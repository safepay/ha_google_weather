"""Binary sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOCATION, CONF_PREFIX, DOMAIN
from .coordinator import GoogleWeatherCoordinator


@dataclass(frozen=True)
class GoogleWeatherBinarySensorDescription(BinarySensorEntityDescription):
    """Describes Google Weather binary sensor entity."""

    value_fn: Callable[[dict], bool] | None = None
    attributes_fn: Callable[[dict], dict] | None = None


BINARY_SENSOR_TYPES: tuple[GoogleWeatherBinarySensorDescription, ...] = (
    GoogleWeatherBinarySensorDescription(
        key="severe_weather_warning",
        name="Severe Weather Warning",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:alert",
        value_fn=lambda data: bool(
            data.get("warnings", []) and 
            any(w.get("severity") == "severe" for w in data.get("warnings", []))
        ),
        attributes_fn=lambda data: {
            "warnings": [
                w for w in data.get("warnings", []) 
                if w.get("severity") == "severe"
            ]
        } if data.get("warnings") else {},
    ),
    GoogleWeatherBinarySensorDescription(
        key="weather_warning",
        name="Weather Warning",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda data: bool(data.get("warnings", [])),
        attributes_fn=lambda data: {
            "warnings": data.get("warnings", []),
            "warning_count": len(data.get("warnings", [])),
        } if data.get("warnings") else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather binary sensor entities."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    prefix = entry.data.get(CONF_PREFIX, "gw")
    location = entry.data.get(CONF_LOCATION, "Home")

    async_add_entities(
        GoogleWeatherBinarySensor(coordinator, entry, description, prefix, location)
        for description in BINARY_SENSOR_TYPES
    )


class GoogleWeatherBinarySensor(
    CoordinatorEntity[GoogleWeatherCoordinator], BinarySensorEntity
):
    """Representation of a Google Weather binary sensor."""

    entity_description: GoogleWeatherBinarySensorDescription

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        description: GoogleWeatherBinarySensorDescription,
        prefix: str,
        location: str,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.coordinator.data and self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return False

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes."""
        if self.coordinator.data and self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return {}
