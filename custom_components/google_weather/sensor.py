"""Sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    UnitOfTime,
    UV_INDEX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ALPHA_LABEL,
    CONF_INCLUDE_HOURLY_FORECAST,
    CONF_INCLUDE_MINUTE_FORECAST,
    CONF_LOCATION,
    DEFAULT_INCLUDE_HOURLY_FORECAST,
    DEFAULT_INCLUDE_MINUTE_FORECAST,
    DOMAIN,
    MINUTE_HORIZONS,
    UNIT_SYSTEM_IMPERIAL,
    VERSION,
)
from .coordinator import GoogleWeatherCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleWeatherSensorDescription(SensorEntityDescription):
    """Describes Google Weather sensor entity."""

    value_fn: Callable[[dict], Any] | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None
    # Minute forecast entities sit on their own device: see ALPHA_LABEL.
    minute: bool = False


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


def get_minute_value(data: dict, key: str) -> Any:
    """Read a derived nowcast value, computed once at fetch time."""
    return (data.get("minute_forecast") or {}).get(key)


def get_onset_attributes(data: dict) -> dict[str, Any]:
    """Attributes for the onset sensor, including the shorter horizons."""
    derived = data.get("minute_forecast") or {}
    attributes: dict[str, Any] = {
        # Publishing the segment width stops a coarse answer reading as precise.
        "onset_precision_minutes": derived.get("onset_precision_minutes"),
        "precipitation_type": derived.get("onset_type"),
        "starts_at": derived.get("starts_at"),
        "segment_minutes": derived.get("cadence_minutes"),
        "forecast_covers_minutes": derived.get("coverage_minutes"),
        "window_end": derived.get("window_end"),
    }
    for horizon in MINUTE_HORIZONS:
        attributes[f"rain_next_{horizon}min"] = derived.get(f"rain_{horizon}min")
    if derived.get("page_truncated"):
        attributes["incomplete_forecast"] = True
    return attributes


MINUTE_SENSOR_TYPES: tuple[GoogleWeatherSensorDescription, ...] = (
    GoogleWeatherSensorDescription(
        key="precipitation_starts_in",
        name="Precipitation Starts In",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:weather-rainy",
        minute=True,
        value_fn=lambda data: get_minute_value(data, "starts_in"),
        attributes_fn=get_onset_attributes,
    ),
    GoogleWeatherSensorDescription(
        key="precipitation_stops_in",
        name="Precipitation Stops In",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:weather-sunny",
        minute=True,
        # Unknown, never the window edge: the data runs out, the rain does not.
        value_fn=lambda data: get_minute_value(data, "stops_in"),
        attributes_fn=lambda data: {
            "truncated_by_window": get_minute_value(data, "truncated_by_window"),
        },
    ),
    GoogleWeatherSensorDescription(
        key="precipitation_rate",
        name="Precipitation Rate",
        native_unit_of_measurement="mm/h",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        suggested_display_precision=2,
        minute=True,
        value_fn=lambda data: get_minute_value(data, "precipitation_rate"),
        attributes_fn=lambda data: {
            # Display only; never rank these by name.
            "intensity": get_minute_value(data, "intensity"),
            # Not the chance of rain. Surfaced for inspection, read by nothing.
            "nowcast_probability": get_minute_value(data, "probability"),
        },
    ),
    GoogleWeatherSensorDescription(
        key="rain_next_60min",
        name="Rain Next 60 Minutes",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        suggested_display_precision=2,
        minute=True,
        value_fn=lambda data: get_minute_value(data, "rain_60min"),
    ),
    GoogleWeatherSensorDescription(
        key="rain_rest_of_window",
        name="Rain Rest Of Forecast",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        suggested_display_precision=2,
        minute=True,
        value_fn=lambda data: get_minute_value(data, "rain_rest_of_window"),
        attributes_fn=lambda data: {
            # A lower bound whenever precipitation runs to the window edge.
            "lower_bound": get_minute_value(data, "truncated_by_window"),
            # Downsampled; the raw segments are never published.
            "timeline": get_minute_value(data, "timeline"),
        },
    ),
)


# Mapping of full cardinal directions to abbreviations
CARDINAL_DIRECTION_MAP = {
    "NORTH": "N",
    "NORTHEAST": "NE",
    "NORTH_NORTHEAST": "NNE",
    "EAST": "E",
    "EAST_NORTHEAST": "ENE",
    "EAST_SOUTHEAST": "ESE",
    "SOUTHEAST": "SE",
    "SOUTH_SOUTHEAST": "SSE",
    "SOUTH": "S",
    "SOUTHWEST": "SW",
    "SOUTH_SOUTHWEST": "SSW",
    "WEST": "W",
    "WEST_NORTHWEST": "WNW",
    "WEST_SOUTHWEST": "WSW",
    "NORTHWEST": "NW",
    "NORTH_NORTHWEST": "NNW",
    "CARDINAL_DIRECTION_UNSPECIFIED": "UNSPECIFIED",
}


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

    if current_data.get(CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST):
        sensor_descriptions += MINUTE_SENSOR_TYPES

    async_add_entities(
        GoogleWeatherSensor(coordinator, entry, description, location)
        for description in sensor_descriptions
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
        if description.minute:
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{entry.entry_id}_minute")},
                "name": f"{location_name} Minute Forecast ({ALPHA_LABEL})",
                "manufacturer": "Google",
                "model": "Weather API - Minute Forecast (Alpha)",
                "sw_version": VERSION,
                "via_device": (DOMAIN, entry.entry_id),
            }
        else:
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
            # The API returns the requested unit system already.
            elif self.entity_description.device_class == SensorDeviceClass.PRECIPITATION_INTENSITY:
                unit = "in/h"

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
        attrs: dict[str, Any] = {}
        if self.coordinator.data and self.entity_description.attributes_fn:
            attrs = self.entity_description.attributes_fn(self.coordinator.data)
            # Filter out None values
            attrs = {k: v for k, v in attrs.items() if v is not None}
        if self.entity_description.minute:
            attrs["alpha"] = ALPHA_LABEL
        return attrs
