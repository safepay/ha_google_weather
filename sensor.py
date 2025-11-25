"""Sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    UV_INDEX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOCATION, CONF_PREFIX, DOMAIN
from .coordinator import GoogleWeatherCoordinator


@dataclass(frozen=True)
class GoogleWeatherSensorDescription(SensorEntityDescription):
    """Describes Google Weather sensor entity."""

    value_fn: Callable[[dict], any] | None = None


SENSOR_TYPES: tuple[GoogleWeatherSensorDescription, ...] = (
    GoogleWeatherSensorDescription(
        key="visibility",
        name="Visibility",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("observations", {}).get("visibility"),
    ),
    GoogleWeatherSensorDescription(
        key="uv_index",
        name="UV Index",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda data: data.get("observations", {}).get("uv_index"),
    ),
    GoogleWeatherSensorDescription(
        key="precipitation",
        name="Precipitation",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("observations", {}).get("precipitation"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather sensor entities."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    prefix = entry.data.get(CONF_PREFIX, "gw")
    location = entry.data.get(CONF_LOCATION, "Home")

    async_add_entities(
        GoogleWeatherSensor(coordinator, entry, description, prefix, location)
        for description in SENSOR_TYPES
    )


class GoogleWeatherSensor(CoordinatorEntity[GoogleWeatherCoordinator], SensorEntity):
    """Representation of a Google Weather sensor."""

    entity_description: GoogleWeatherSensorDescription

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        description: GoogleWeatherSensorDescription,
        prefix: str,
        location: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        
        location_slug = location.lower().replace(" ", "_")
        self._attr_name = f"{location} {description.name}"
        self._attr_unique_id = f"{prefix}_{location_slug}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Google Weather - {location}",
            "manufacturer": "Google",
            "model": "Weather API",
        }

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data and self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None
