"""Google Weather integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, ENDPOINT_DAILY, ENDPOINT_HOURLY, CONF_INCLUDE_ALERTS
from .coordinator import GoogleWeatherCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.WEATHER, Platform.SENSOR, Platform.BINARY_SENSOR]

SERVICE_GET_FORECAST = "get_forecast"
ATTR_FORECAST_TYPE = "forecast_type"
ATTR_ENTITY_ID = "entity_id"

SERVICE_GET_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_FORECAST_TYPE): vol.In(["daily", "hourly"]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Weather from a config entry."""
    # Create coordinator
    coordinator = GoogleWeatherCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register service for on-demand forecast fetching
    async def async_get_forecast(call: ServiceCall) -> ServiceResponse:
        """Handle the get_forecast service call."""
        entity_id = call.data[ATTR_ENTITY_ID]
        forecast_type = call.data[ATTR_FORECAST_TYPE]

        # Find the coordinator for this entity
        for entry_id, coord in hass.data[DOMAIN].items():
            if isinstance(coord, GoogleWeatherCoordinator):
                # Fetch the forecast on demand
                endpoint = ENDPOINT_DAILY if forecast_type == "daily" else ENDPOINT_HOURLY
                forecast_data = await coord.async_fetch_forecast_on_demand(endpoint)

                _LOGGER.info(
                    "On-demand %s forecast fetched for %s: %d items",
                    forecast_type,
                    entity_id,
                    len(forecast_data),
                )

                return {"forecast": forecast_data}

        _LOGGER.error("Could not find coordinator for entity %s", entity_id)
        return {"forecast": []}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FORECAST,
        async_get_forecast,
        schema=SERVICE_GET_FORECAST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Get current configuration (data + new options)
    current_config = {**entry.data, **entry.options}
    alerts_enabled = current_config.get(CONF_INCLUDE_ALERTS, True)

    # If alerts are now disabled, remove any existing alert entities
    if not alerts_enabled:
        _LOGGER.info("Alerts disabled - removing orphaned alert binary sensor entities")
        await _remove_alert_entities(hass, entry)

    # Reload the entry to apply changes
    await hass.config_entries.async_reload(entry.entry_id)


async def _remove_alert_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove alert binary sensor entities from the entity registry."""
    from .const import CONF_LOCATION

    entity_registry = er.async_get(hass)
    location = entry.data.get(CONF_LOCATION, "home")
    location_slug = location.lower().replace(" ", "_")

    # Alert sensor keys that need to be removed
    alert_sensor_keys = ["weather_alert", "severe_weather_alert", "urgent_weather_alert"]

    for sensor_key in alert_sensor_keys:
        unique_id = f"{location_slug}_{sensor_key}"
        entity_id = entity_registry.async_get_entity_id(
            Platform.BINARY_SENSOR, DOMAIN, unique_id
        )

        if entity_id:
            _LOGGER.info("Removing orphaned alert entity: %s (unique_id: %s)", entity_id, unique_id)
            entity_registry.async_remove(entity_id)
        else:
            _LOGGER.debug("Alert entity not found in registry: %s", unique_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

        # Unregister service if this was the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_GET_FORECAST)

    return unload_ok
