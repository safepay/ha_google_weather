"""Sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UV_INDEX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    CARDINAL_DIRECTION_MAP,
    CONF_FORECAST_DAYS,
    CONF_INCLUDE_FORECAST_SENSORS,
    CONF_INCLUDE_HOURLY_FORECAST,
    CONF_LOCATION,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_INCLUDE_FORECAST_SENSORS,
    DEFAULT_INCLUDE_HOURLY_FORECAST,
    DOMAIN,
    MAX_FORECAST_DAYS,
    UNIT_SYSTEM_IMPERIAL,
    VERSION,
)
from .coordinator import GoogleWeatherCoordinator
from .forecast_data import (
    KEY_HIGH,
    KEY_ICON_DESCRIPTOR,
    KEY_LOW,
    KEY_PRECIPITATION,
    KEY_PRECIPITATION_PROBABILITY,
    KEY_SNOW,
    get_forecast_attributes,
    get_forecast_high,
    get_forecast_icon_descriptor,
    get_forecast_low,
    get_forecast_precipitation,
    get_forecast_probability,
    get_forecast_snow,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleWeatherSensorDescription(SensorEntityDescription):
    """Describes Google Weather sensor entity."""

    value_fn: Callable[[dict], Any] | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None


@dataclass(frozen=True)
class GoogleWeatherForecastDescription(SensorEntityDescription):
    """Describes one forecast metric, before a day offset is applied.

    Separate from the above because these read a day out of a list rather than
    the whole payload, so the callables take the offset as a second argument.
    """

    value_fn: Callable[[list, int], Any] | None = None
    attributes_fn: Callable[[list, int], dict[str, Any]] | None = None


def get_current_value(data: dict, *keys: str) -> Any:
    """Safely get nested value from current conditions."""
    current = data.get("current", {})
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, {})
        else:
            return None
    return current if not isinstance(current, dict) else None


def get_snow_forecast_next_24h(data: dict) -> float | None:
    """Return cached 24-hour snow forecast total from coordinator data."""
    return data.get("snow_forecast_24h")


# One entry per forecast metric, instantiated once per day offset. Keeping the
# metric and the day apart means the table is built once at import, not rebuilt
# on every call that only wants the keys.
FORECAST_METRICS: tuple[GoogleWeatherForecastDescription, ...] = (
    GoogleWeatherForecastDescription(
        key=KEY_HIGH,
        name="Forecast High",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-high",
        suggested_display_precision=1,
        # No state_class: a prediction does not belong in temperature stats.
        # Also carries the rest of the day, as attributes.
        value_fn=get_forecast_high,
        attributes_fn=get_forecast_attributes,
    ),
    GoogleWeatherForecastDescription(
        key=KEY_LOW,
        name="Forecast Low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-low",
        suggested_display_precision=1,
        value_fn=get_forecast_low,
    ),
    GoogleWeatherForecastDescription(
        key=KEY_PRECIPITATION,
        name="Forecast Precipitation",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        icon="mdi:weather-pouring",
        suggested_display_precision=1,
        value_fn=get_forecast_precipitation,
    ),
    GoogleWeatherForecastDescription(
        key=KEY_SNOW,
        name="Forecast Snow",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        icon="mdi:weather-snowy-heavy",
        suggested_display_precision=1,
        value_fn=get_forecast_snow,
    ),
    GoogleWeatherForecastDescription(
        key=KEY_PRECIPITATION_PROBABILITY,
        name="Forecast Precipitation Probability",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:weather-rainy",
        value_fn=get_forecast_probability,
    ),
    GoogleWeatherForecastDescription(
        key=KEY_ICON_DESCRIPTOR,
        name="Forecast Icon Descriptor",
        icon="mdi:weather-partly-cloudy",
        value_fn=get_forecast_icon_descriptor,
    ),
)


# Observational Sensors
SENSOR_TYPES: tuple[GoogleWeatherSensorDescription, ...] = (
    # Temperature sensors
    GoogleWeatherSensorDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "temperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="feels_like",
        name="Feels Like Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "feelsLikeTemperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="dew_point",
        name="Dew Point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "dewPoint", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="heat_index",
        name="Heat Index",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "heatIndex", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="wind_chill",
        name="Wind Chill",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "windChill", "degrees"),
    ),
    # Humidity
    GoogleWeatherSensorDescription(
        key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("relativeHumidity"),
    ),
    # Pressure
    GoogleWeatherSensorDescription(
        key="pressure",
        name="Pressure",
        native_unit_of_measurement=UnitOfPressure.MBAR,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: get_current_value(data, "airPressure", "meanSeaLevelMillibars"),
    ),
    # Wind sensors
    GoogleWeatherSensorDescription(
        key="wind_speed",
        name="Wind Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=lambda data: get_current_value(data, "wind", "speed", "value"),
        attributes_fn=lambda data: {
            "direction": get_current_value(data, "wind", "direction", "degrees"),
            "cardinal": get_current_value(data, "wind", "direction", "cardinal"),
        },
    ),
    GoogleWeatherSensorDescription(
        key="wind_gust",
        name="Wind Gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
        value_fn=lambda data: get_current_value(data, "wind", "gust", "value"),
    ),
    GoogleWeatherSensorDescription(
        key="wind_direction",
        name="Wind Direction",
        icon="mdi:compass",
        value_fn=lambda data: get_current_value(data, "wind", "direction", "cardinal"),
        attributes_fn=lambda data: {
            "degrees": get_current_value(data, "wind", "direction", "degrees"),
        },
    ),
    GoogleWeatherSensorDescription(
        key="wind_cardinal",
        name="Wind Cardinal",
        icon="mdi:compass-rose",
        value_fn=lambda data: CARDINAL_DIRECTION_MAP.get(
            get_current_value(data, "wind", "direction", "cardinal")
        ),
    ),
    GoogleWeatherSensorDescription(
        key="wind_degrees",
        name="Wind Degrees",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass",
        value_fn=lambda data: get_current_value(data, "wind", "direction", "degrees"),
    ),
    # Visibility
    GoogleWeatherSensorDescription(
        key="visibility",
        name="Visibility",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye",
        value_fn=lambda data: get_current_value(data, "visibility", "distance"),
    ),
    # Cloud cover
    GoogleWeatherSensorDescription(
        key="cloud_cover",
        name="Cloud Cover",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cloud-percent",
        value_fn=lambda data: data.get("current", {}).get("cloudCover"),
    ),
    # UV Index
    GoogleWeatherSensorDescription(
        key="uv_index",
        name="UV Index",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda data: data.get("current", {}).get("uvIndex"),
    ),
    # Precipitation
    GoogleWeatherSensorDescription(
        key="precipitation_probability",
        name="Precipitation Probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda data: get_current_value(data, "precipitation", "probability", "percent"),
        attributes_fn=lambda data: {
            "type": get_current_value(data, "precipitation", "probability", "type"),
        },
    ),
    GoogleWeatherSensorDescription(
        key="precipitation_amount",
        name="Precipitation Amount",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda data: get_current_value(data, "precipitation", "qpf", "quantity"),
    ),
    GoogleWeatherSensorDescription(
        key="snow_amount",
        name="Snow Amount",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy",
        value_fn=lambda data: get_current_value(data, "precipitation", "snowQpf", "quantity"),
    ),
    GoogleWeatherSensorDescription(
        key="snow_forecast_24h",
        name="Snow Forecast (24h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy-rainy",
        value_fn=get_snow_forecast_next_24h,
        suggested_display_precision=3,
    ),
    GoogleWeatherSensorDescription(
        key="thunderstorm_probability",
        name="Thunderstorm Probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-lightning",
        value_fn=lambda data: data.get("current", {}).get("thunderstormProbability"),
    ),
    # Historical data (24 hours)
    GoogleWeatherSensorDescription(
        key="temp_change_24h",
        name="Temperature Change (24h)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-chevron-up",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "temperatureChange", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="max_temp_24h",
        name="Max Temperature (24h)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-high",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "maxTemperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="min_temp_24h",
        name="Min Temperature (24h)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-low",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "minTemperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="precipitation_24h",
        name="Precipitation (24h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "qpf", "quantity"),
    ),
    GoogleWeatherSensorDescription(
        key="snow_24h",
        name="Snow (24h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy-heavy",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "snowQpf", "quantity"),
    ),
    # Weather condition
    GoogleWeatherSensorDescription(
        key="weather_condition",
        name="Weather Condition",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: get_current_value(data, "weatherCondition", "description", "text"),
        attributes_fn=lambda data: {
            "type": get_current_value(data, "weatherCondition", "type"),
            "icon_base_uri": get_current_value(data, "weatherCondition", "iconBaseUri"),
            "is_daytime": data.get("current", {}).get("isDaytime"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather sensor entities."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]

    location = entry.data.get(CONF_LOCATION, "home")
    current_data = {**entry.data, **entry.options}
    include_hourly = current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST)

    sensor_descriptions = (
        SENSOR_TYPES
        if include_hourly
        else tuple(description for description in SENSOR_TYPES if description.key != "snow_forecast_24h")
    )

    async_add_entities(
        GoogleWeatherSensor(coordinator, entry, description, location)
        for description in sensor_descriptions
    )

    # Read from the cached daily response, so no extra API calls.
    if current_data.get(
        CONF_INCLUDE_FORECAST_SENSORS, DEFAULT_INCLUDE_FORECAST_SENSORS
    ):
        days = min(
            current_data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
            MAX_FORECAST_DAYS,
        )
        async_add_entities(
            GoogleWeatherForecastSensor(coordinator, entry, metric, offset, location)
            for offset in range(days)
            for metric in FORECAST_METRICS
        )


class GoogleWeatherSensor(CoordinatorEntity[GoogleWeatherCoordinator], SensorEntity):
    """Representation of a Google Weather sensor."""

    _attr_has_entity_name = False
    entity_description: GoogleWeatherSensorDescription

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        description: GoogleWeatherSensorDescription,
        location: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        # Use location directly for entity ID (slugified)
        location_slug = location.lower().replace(" ", "_")

        # Create friendly name from location (title case)
        location_name = location.replace("_", " ").title()

        # Set unique_id, explicit friendly name, and device info (has_entity_name = False)
        # Use separate device linked to weather device via via_device
        self._attr_unique_id = f"{location_slug}_{description.key}"
        self._attr_name = f"{location_name} {description.name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_sensors")},
            "name": f"{location_name} Observational Sensors",
            "manufacturer": "Google",
            "model": "Weather API - Sensors",
            "sw_version": VERSION,
            "via_device": (DOMAIN, entry.entry_id),
        }

        # Home Assistant builds a new entity's id from the device name followed
        # by the entity name, and drops the device name only when the entity
        # name starts with it. That gives
        # sensor.home_observational_sensors_home_temperature here, so ask for
        # the id these have always had. It applies only when an entity is first
        # created; one already in the registry keeps the id it has.
        self.entity_id = f"sensor.{slugify(self._attr_name)}"

        # Read unit system from coordinator (auto-detected from HA config)
        self._unit_system = coordinator.unit_system

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement based on configured unit system.

        Override entity_description units when imperial is selected,
        since API returns values in the requested unit system.
        """
        unit = None
        if self._unit_system == UNIT_SYSTEM_IMPERIAL:
            # Override temperature units to Fahrenheit
            if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
                unit = UnitOfTemperature.FAHRENHEIT
            # Override wind speed units to MPH
            elif self.entity_description.device_class == SensorDeviceClass.WIND_SPEED:
                unit = UnitOfSpeed.MILES_PER_HOUR
            # Override visibility units to Miles
            elif self.entity_description.key == "visibility":
                unit = UnitOfLength.MILES
            # Override precipitation units to Inches
            elif self.entity_description.device_class == SensorDeviceClass.PRECIPITATION:
                unit = UnitOfPrecipitationDepth.INCHES

        # Use default unit from entity description for metric
        if unit is None:
            unit = self.entity_description.native_unit_of_measurement

        return unit

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data and self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data and self.entity_description.attributes_fn:
            attrs = self.entity_description.attributes_fn(self.coordinator.data)
            # Filter out None values
            return {k: v for k, v in attrs.items() if v is not None}
        return {}


class GoogleWeatherForecastSensor(GoogleWeatherSensor):
    """A forecast-day sensor: as above, but on the Forecast Sensors device.

    Subclassed so the naming and unit logic stays in one place. The offset goes
    into both key and name, so the existing naming chain yields
    sensor.<location>_<metric>_<offset> unchanged.
    """

    entity_description: GoogleWeatherForecastDescription

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        metric: GoogleWeatherForecastDescription,
        offset: int,
        location: str,
    ) -> None:
        """Initialize the sensor, then move it to its own device."""
        self._offset = offset
        super().__init__(
            coordinator,
            entry,
            replace(
                metric,
                key=f"{metric.key}_{offset}",
                name=f"{metric.name} {offset}",
            ),
            location,
        )

        location_name = location.replace("_", " ").title()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_forecast")},
            "name": f"{location_name} Forecast Sensors",
            "manufacturer": "Google",
            "model": "Weather API - Forecast Sensors",
            "sw_version": VERSION,
            "via_device": (DOMAIN, entry.entry_id),
        }

    @property
    def _forecast_days(self) -> list[dict[str, Any]]:
        """The cached daily forecast, trimmed by the coordinator to start today."""
        return (self.coordinator.data or {}).get("daily_forecast") or []

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self._forecast_days, self._offset)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.entity_description.attributes_fn:
            return {}
        attrs = self.entity_description.attributes_fn(
            self._forecast_days, self._offset
        )
        # Filter out None values
        return {key: value for key, value in attrs.items() if value is not None}
