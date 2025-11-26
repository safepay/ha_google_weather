"""Sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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

from .const import CONF_LOCATION, DOMAIN
from .coordinator import GoogleWeatherCoordinator


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
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:weather-rainy",
        value_fn=lambda data: get_current_value(data, "precipitation", "qpf", "quantity"),
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
        icon="mdi:thermometer-chevron-up",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "temperatureChange", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="max_temp_24h",
        name="Max Temperature (24h)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-high",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "maxTemperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="min_temp_24h",
        name="Min Temperature (24h)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-low",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "minTemperature", "degrees"),
    ),
    GoogleWeatherSensorDescription(
        key="precipitation_24h",
        name="Precipitation (24h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        icon="mdi:weather-pouring",
        value_fn=lambda data: get_current_value(data, "currentConditionsHistory", "qpf", "quantity"),
    ),
    # Weather condition
    GoogleWeatherSensorDescription(
        key="weather_condition",
        name="Weather Condition",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: get_current_value(data, "weatherCondition", "description", "text"),
        attributes_fn=lambda data: {
            "type": get_current_value(data, "weatherCondition", "type"),
            "icon": get_current_value(data, "weatherCondition", "iconBaseUri"),
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

    async_add_entities(
        GoogleWeatherSensor(coordinator, entry, description, location)
        for description in SENSOR_TYPES
    )


class GoogleWeatherSensor(CoordinatorEntity[GoogleWeatherCoordinator], SensorEntity):
    """Representation of a Google Weather sensor."""

    entity_description: GoogleWeatherSensorDescription
    _attr_has_entity_name = True

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

        # Set entity name to just the sensor type (device name will be prefixed)
        self._attr_name = description.name
        self._attr_unique_id = f"{location_slug}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_sensors")},
            "name": location_name,  # Just the location, not "Location Observational Sensors"
            "manufacturer": "Google",
            "model": "Weather API - Sensors",
            "sw_version": "v1",
            "via_device": (DOMAIN, entry.entry_id),
        }

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
