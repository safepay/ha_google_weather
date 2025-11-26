"""Config flow for Google Weather integration."""
from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ALERTS_DAY_INTERVAL,
    CONF_ALERTS_NIGHT_INTERVAL,
    CONF_API_KEY,
    CONF_CURRENT_DAY_INTERVAL,
    CONF_CURRENT_NIGHT_INTERVAL,
    CONF_DAILY_DAY_INTERVAL,
    CONF_DAILY_NIGHT_INTERVAL,
    CONF_HOURLY_DAY_INTERVAL,
    CONF_HOURLY_NIGHT_INTERVAL,
    CONF_LOCATION,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_UNIT_SYSTEM,
    DEFAULT_ALERTS_DAY_INTERVAL,
    DEFAULT_ALERTS_NIGHT_INTERVAL,
    DEFAULT_CURRENT_DAY_INTERVAL,
    DEFAULT_CURRENT_NIGHT_INTERVAL,
    DEFAULT_DAILY_DAY_INTERVAL,
    DEFAULT_DAILY_NIGHT_INTERVAL,
    DEFAULT_HOURLY_DAY_INTERVAL,
    DEFAULT_HOURLY_NIGHT_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_UNIT_SYSTEM,
    DOMAIN,
    API_BASE_URL,
    UNIT_SYSTEMS,
)

_LOGGER = logging.getLogger(__name__)


class GoogleWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self.api_key: str | None = None
        self.user_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API key input."""
        errors = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()

            # Validate API key by making a test request
            try:
                is_valid = await self.hass.async_add_executor_job(
                    self._validate_api_key, api_key
                )

                if is_valid:
                    self.api_key = api_key
                    return await self.async_step_location()
                else:
                    errors["base"] = "invalid_api_key"
            except Exception as err:
                _LOGGER.error("Error validating API key: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )

    def _validate_api_key(self, api_key: str) -> bool:
        """Validate the API key by making a test request."""
        try:
            # Use a default location for testing (Sydney, Australia)
            url = f"{API_BASE_URL}/currentConditions:lookup"
            params = {
                "key": api_key,
                "location.latitude": -33.8688,
                "location.longitude": 151.2093,
            }
            response = requests.get(url, params=params, timeout=10)

            # API key is valid if we get 200 or even 400 (bad request but key is accepted)
            # 401/403 means invalid API key
            if response.status_code in [200, 400]:
                return True
            elif response.status_code in [401, 403]:
                return False
            else:
                # Other errors, consider it connection issue
                return False
        except requests.RequestException:
            return False

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure location and unit system."""
        errors = {}

        if user_input is not None:
            # Validate latitude and longitude
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if not (-90 <= latitude <= 90):
                errors[CONF_LATITUDE] = "invalid_latitude"
            if not (-180 <= longitude <= 180):
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                # Store location data
                self.user_data = {
                    CONF_LOCATION: user_input[CONF_LOCATION],
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                    CONF_UNIT_SYSTEM: user_input[CONF_UNIT_SYSTEM],
                }
                return await self.async_step_intervals()

        # Default to Home Assistant's configured location
        default_latitude = self.hass.config.latitude
        default_longitude = self.hass.config.longitude

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION, default="home"): str,
                    vol.Required(CONF_LATITUDE, default=default_latitude): vol.Coerce(float),
                    vol.Required(CONF_LONGITUDE, default=default_longitude): vol.Coerce(float),
                    vol.Required(CONF_UNIT_SYSTEM, default=DEFAULT_UNIT_SYSTEM): vol.In(UNIT_SYSTEMS),
                }
            ),
            errors=errors,
        )

    async def async_step_intervals(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure update intervals for API endpoints."""
        if user_input is not None:
            # Merge all data and create entry
            final_data = {
                CONF_API_KEY: self.api_key,
                **self.user_data,
                **user_input,
            }

            location_name = self.user_data[CONF_LOCATION]
            return self.async_create_entry(
                title=f"Google Weather - {location_name}",
                data=final_data,
            )

        return self.async_show_form(
            step_id="intervals",
            data_schema=vol.Schema(
                {
                    # Current conditions intervals
                    vol.Optional(
                        CONF_CURRENT_DAY_INTERVAL,
                        default=DEFAULT_CURRENT_DAY_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_CURRENT_NIGHT_INTERVAL,
                        default=DEFAULT_CURRENT_NIGHT_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Daily forecast intervals
                    vol.Optional(
                        CONF_DAILY_DAY_INTERVAL,
                        default=DEFAULT_DAILY_DAY_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_DAILY_NIGHT_INTERVAL,
                        default=DEFAULT_DAILY_NIGHT_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Hourly forecast intervals
                    vol.Optional(
                        CONF_HOURLY_DAY_INTERVAL,
                        default=DEFAULT_HOURLY_DAY_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_HOURLY_NIGHT_INTERVAL,
                        default=DEFAULT_HOURLY_NIGHT_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Weather alerts intervals
                    vol.Optional(
                        CONF_ALERTS_DAY_INTERVAL,
                        default=DEFAULT_ALERTS_DAY_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_ALERTS_NIGHT_INTERVAL,
                        default=DEFAULT_ALERTS_NIGHT_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Night time period
                    vol.Optional(
                        CONF_NIGHT_START,
                        default=DEFAULT_NIGHT_START,
                    ): str,
                    vol.Optional(
                        CONF_NIGHT_END,
                        default=DEFAULT_NIGHT_END,
                    ): str,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GoogleWeatherOptionsFlow:
        """Get the options flow for this handler."""
        return GoogleWeatherOptionsFlow(config_entry)


class GoogleWeatherOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Google Weather."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # Validate latitude and longitude
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if not (-90 <= latitude <= 90):
                errors[CONF_LATITUDE] = "invalid_latitude"
            if not (-180 <= longitude <= 180):
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                # Update options
                return self.async_create_entry(title="", data=user_input)

        # Get current values from config_entry (data or options)
        current_data = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LATITUDE,
                        default=current_data.get(CONF_LATITUDE),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_LONGITUDE,
                        default=current_data.get(CONF_LONGITUDE),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_UNIT_SYSTEM,
                        default=current_data.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM),
                    ): vol.In(UNIT_SYSTEMS),
                    # Update intervals
                    vol.Optional(
                        CONF_CURRENT_DAY_INTERVAL,
                        default=current_data.get(CONF_CURRENT_DAY_INTERVAL, DEFAULT_CURRENT_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_CURRENT_NIGHT_INTERVAL,
                        default=current_data.get(CONF_CURRENT_NIGHT_INTERVAL, DEFAULT_CURRENT_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_DAILY_DAY_INTERVAL,
                        default=current_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_DAILY_NIGHT_INTERVAL,
                        default=current_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_HOURLY_DAY_INTERVAL,
                        default=current_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_HOURLY_NIGHT_INTERVAL,
                        default=current_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_ALERTS_DAY_INTERVAL,
                        default=current_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_ALERTS_NIGHT_INTERVAL,
                        default=current_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_NIGHT_START,
                        default=current_data.get(CONF_NIGHT_START, DEFAULT_NIGHT_START),
                    ): str,
                    vol.Optional(
                        CONF_NIGHT_END,
                        default=current_data.get(CONF_NIGHT_END, DEFAULT_NIGHT_END),
                    ): str,
                }
            ),
            errors=errors,
        )
