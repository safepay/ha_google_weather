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
    UV_INDEX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util import dt as dt_util

from .const import (
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

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleWeatherSensorDescription(SensorEntityDescription):
    """Describes Google Weather sensor entity."""

    value_fn: Callable[[dict], Any] | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None


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


# Carried under a "night_" prefix; the daytime block stays unprefixed all day.
NIGHT_ATTRIBUTES = (
    "condition",
    "condition_type",
    "precipitation_probability",
    "precipitation",
    "cloud_cover",
    "wind_speed",
)


def get_forecast_day(data: dict, offset: int) -> dict[str, Any]:
    """Return one day of the cached daily forecast, counting today as 0.

    Today is not reliably ``forecastDays[0]``: the cache can be a polling
    interval old, so just after midnight the first entry may still be
    yesterday. Count from the first day whose interval has not ended.
    """
    daily = data.get("daily_forecast") or []
    now = dt_util.utcnow()
    for index, day in enumerate(daily):
        end_time = (day.get("interval") or {}).get("endTime")
        if not end_time:
            continue
        end = dt_util.parse_datetime(end_time)
        if end and end > now:
            wanted = index + offset
            return daily[wanted] if wanted < len(daily) else {}
    return daily[offset] if offset < len(daily) else {}


def _degrees(day: dict[str, Any], key: str) -> float | None:
    """Read one of the day's temperature fields."""
    return (day.get(key) or {}).get("degrees")


def _precipitation(block: dict[str, Any], key: str) -> float | None:
    """Read an accumulation out of a day part's precipitation."""
    return ((block.get("precipitation") or {}).get(key) or {}).get("quantity")


def _probability(block: dict[str, Any]) -> int | None:
    """Read a day part's chance of precipitation."""
    return ((block.get("precipitation") or {}).get("probability") or {}).get("percent")


def _day_part_attributes(block: dict[str, Any]) -> dict[str, Any]:
    """Flatten one daytimeForecast or nighttimeForecast block."""
    condition = block.get("weatherCondition") or {}
    wind = block.get("wind") or {}
    direction = wind.get("direction") or {}
    return {
        "condition": (condition.get("description") or {}).get("text"),
        "condition_type": condition.get("type"),
        "humidity": block.get("relativeHumidity"),
        "uv_index": block.get("uvIndex"),
        "cloud_cover": block.get("cloudCover"),
        "precipitation_probability": _probability(block),
        "precipitation_type": (
            (block.get("precipitation") or {}).get("probability") or {}
        ).get("type"),
        "precipitation": _precipitation(block, "qpf"),
        "snow": _precipitation(block, "snowQpf"),
        "thunderstorm_probability": block.get("thunderstormProbability"),
        "wind_speed": (wind.get("speed") or {}).get("value"),
        "wind_gust": (wind.get("gust") or {}).get("value"),
        "wind_bearing": direction.get("degrees"),
        "wind_direction": CARDINAL_DIRECTION_MAP.get(direction.get("cardinal")),
    }


def get_forecast_precipitation(data: dict, offset: int, key: str) -> float | None:
    """Total one accumulation across the day's two parts, which do not overlap."""
    day = get_forecast_day(data, offset)
    amounts = [
        _precipitation(day.get(part) or {}, key)
        for part in ("daytimeForecast", "nighttimeForecast")
    ]
    present = [amount for amount in amounts if amount is not None]
    # Rounded: summing floats out of JSON leaves 0.30000000000000004.
    return round(sum(present), 3) if present else None


def get_forecast_probability(data: dict, offset: int) -> int | None:
    """Return the day's chance of precipitation, as the higher of its parts.

    Not combined as independent chances: both halves are driven by the same
    system, so that would overstate the risk.
    """
    day = get_forecast_day(data, offset)
    chances = [
        _probability(day.get(part) or {})
        for part in ("daytimeForecast", "nighttimeForecast")
    ]
    present = [chance for chance in chances if chance is not None]
    return max(present) if present else None


def get_forecast_high(data: dict, offset: int) -> float | None:
    """Return the day's forecast high, the state of the rollup sensor."""
    return _degrees(get_forecast_day(data, offset), "maxTemperature")


def get_forecast_attributes(data: dict, offset: int) -> dict[str, Any]:
    """Expose the rest of the day, which the weather entity's schema drops."""
    day = get_forecast_day(data, offset)
    if not day:
        return {}

    daytime = day.get("daytimeForecast") or {}
    nighttime = day.get("nighttimeForecast") or {}
    sun = day.get("sunEvents") or {}
    moon = day.get("moonEvents") or {}

    attributes: dict[str, Any] = {
        "temperature_high": _degrees(day, "maxTemperature"),
        "temperature_low": _degrees(day, "minTemperature"),
        "feels_like_high": _degrees(day, "feelsLikeMaxTemperature"),
        "feels_like_low": _degrees(day, "feelsLikeMinTemperature"),
        "max_heat_index": _degrees(day, "maxHeatIndex"),
        "sunrise": sun.get("sunriseTime"),
        "sunset": sun.get("sunsetTime"),
        "moon_phase": moon.get("moonPhase"),
        # The parts do not tile midnight to midnight, so publish the real window.
        "forecast_window_start": (daytime.get("interval") or {}).get("startTime"),
        "forecast_window_end": (nighttime.get("interval") or {}).get("endTime"),
        **_day_part_attributes(daytime),
    }

    night = _day_part_attributes(nighttime)
    attributes.update({f"night_{key}": night[key] for key in NIGHT_ATTRIBUTES})

    return attributes


def build_forecast_descriptions(
    offset: int,
) -> tuple[GoogleWeatherSensorDescription, ...]:
    """Build the sensor set for one forecast day.

    The index goes in both key and name, so the existing naming chain yields
    sensor.<location>_<key> unchanged.
    """
    label = f"Day {offset}"
    return (
        GoogleWeatherSensorDescription(
            key=f"forecast_day_{offset}",
            name=f"Forecast {label}",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            icon="mdi:sun-thermometer",
            suggested_display_precision=1,
            # No state_class: a prediction does not belong in temperature stats.
            value_fn=lambda data, offset=offset: get_forecast_high(data, offset),
            attributes_fn=lambda data, offset=offset: get_forecast_attributes(
                data, offset
            ),
        ),
        GoogleWeatherSensorDescription(
            key=f"precipitation_forecast_day_{offset}",
            name=f"Precipitation Forecast {label}",
            native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
            device_class=SensorDeviceClass.PRECIPITATION,
            icon="mdi:weather-pouring",
            suggested_display_precision=1,
            value_fn=lambda data, offset=offset: get_forecast_precipitation(
                data, offset, "qpf"
            ),
        ),
        GoogleWeatherSensorDescription(
            key=f"snow_forecast_day_{offset}",
            name=f"Snow Forecast {label}",
            native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
            device_class=SensorDeviceClass.PRECIPITATION,
            icon="mdi:weather-snowy-heavy",
            suggested_display_precision=1,
            value_fn=lambda data, offset=offset: get_forecast_precipitation(
                data, offset, "snowQpf"
            ),
        ),
        GoogleWeatherSensorDescription(
            key=f"precipitation_probability_day_{offset}",
            name=f"Precipitation Probability {label}",
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:weather-rainy",
            value_fn=lambda data, offset=offset: get_forecast_probability(
                data, offset
            ),
        ),
    )


def forecast_sensor_keys(days: int = MAX_FORECAST_DAYS) -> list[str]:
    """Every forecast sensor key up to a day count, for registry cleanup."""
    return [
        description.key
        for offset in range(days)
        for description in build_forecast_descriptions(offset)
    ]


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
            GoogleWeatherForecastSensor(coordinator, entry, description, location)
            for offset in range(days)
            for description in build_forecast_descriptions(offset)
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
    """A forecast-day sensor: as above, but on the Forecast device.

    Subclassed so the naming and unit logic stays in one place.
    """

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        description: GoogleWeatherSensorDescription,
        location: str,
    ) -> None:
        """Initialize the sensor, then move it to its own device."""
        super().__init__(coordinator, entry, description, location)

        location_name = location.replace("_", " ").title()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_forecast")},
            "name": f"{location_name} Forecast",
            "manufacturer": "Google",
            "model": "Weather API - Forecast",
            "sw_version": VERSION,
            "via_device": (DOMAIN, entry.entry_id),
        }
