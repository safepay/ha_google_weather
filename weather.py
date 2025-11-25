"""Weather platform for Google Weather integration."""
from __future__ import annotations

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOCATION, CONF_PREFIX, DOMAIN
from .coordinator import GoogleWeatherCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather entity."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    prefix = entry.data.get(CONF_PREFIX, "gw")
    location = entry.data.get(CONF_LOCATION, "Home")

    async_add_entities([GoogleWeatherEntity(coordinator, entry, prefix, location)])


class GoogleWeatherEntity(CoordinatorEntity[GoogleWeatherCoordinator], WeatherEntity):
    """Representation of a Google Weather entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        prefix: str,
        location: str,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        
        self._attr_name = f"{location} Weather"
        self._attr_unique_id = f"{prefix}_{location.lower().replace(' ', '_')}_weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Google Weather - {location}",
            "manufacturer": "Google",
            "model": "Weather API",
        }

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if self.coordinator.data and "current" in self.coordinator.data:
            return self.coordinator.data["current"].get("temperature")
        return None

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if self.coordinator.data and "current" in self.coordinator.data:
            return self.coordinator.data["current"].get("humidity")
        return None

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if self.coordinator.data and "current" in self.coordinator.data:
            return self.coordinator.data["current"].get("pressure")
        return None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if self.coordinator.data and "current" in self.coordinator.data:
            return self.coordinator.data["current"].get("wind_speed")
        return None

    @property
    def condition(self) -> str | None:
        """Return the weather condition."""
        if self.coordinator.data and "current" in self.coordinator.data:
            return self.coordinator.data["current"].get("condition")
        return None
