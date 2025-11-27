"""Google Weather integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, ENDPOINT_DAILY, ENDPOINT_HOURLY
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
    async def async_get_forecast(call: ServiceCall) -> dict[str, Any]:
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
    )

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

        # Unregister service if this was the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_GET_FORECAST)

    return unload_ok
