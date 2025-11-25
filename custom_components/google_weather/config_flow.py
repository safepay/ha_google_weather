"""Config flow for Google Weather integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_ALERTS_DAY_INTERVAL,
    CONF_ALERTS_NIGHT_INTERVAL,
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
    OAUTH2_SCOPES,
    UNIT_SYSTEMS,
)

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Config flow to handle Google Weather OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": " ".join(OAUTH2_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow start."""
        # Check if Google application credentials are configured
        implementations = (
            await config_entry_oauth2_flow.async_get_implementations(
                self.hass, self.DOMAIN
            )
        )

        if not implementations:
            return self.async_abort(reason="missing_credentials")

        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> FlowResult:
        """Create an entry for Google Weather after OAuth authentication."""
        # After OAuth is complete, ask for location and prefix
        self.oauth_data = data
        self.user_data = {}
        return await self.async_step_location()

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure location and prefix."""
        errors = {}

        if user_input is not None:
            # Validate latitude and longitude
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)
            
            if not (-90 <= latitude <= 90):
                errors[CONF_LATITUDE] = "invalid_latitude"
            elif not (-180 <= longitude <= 180):
                errors[CONF_LONGITUDE] = "invalid_longitude"
            else:
                # Create the config entry
                location_name = user_input[CONF_LOCATION]
                prefix = user_input.get(CONF_PREFIX, DEFAULT_PREFIX)
                
                await self.async_set_unique_id(f"{prefix}_{location_name}")
                self._abort_if_unique_id_configured()

                unit_system = user_input.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)

                # Store user input for later steps
                self.user_data = {
                    CONF_LOCATION: location_name,
                    CONF_PREFIX: prefix,
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                    CONF_UNIT_SYSTEM: unit_system,
                }

                # Ask if user wants to configure update intervals
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
                **self.oauth_data,
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
            description_placeholders={
                "current_day": str(DEFAULT_CURRENT_DAY_INTERVAL),
                "current_night": str(DEFAULT_CURRENT_NIGHT_INTERVAL),
                "daily_day": str(DEFAULT_DAILY_DAY_INTERVAL),
                "daily_night": str(DEFAULT_DAILY_NIGHT_INTERVAL),
                "hourly_day": str(DEFAULT_HOURLY_DAY_INTERVAL),
                "hourly_night": str(DEFAULT_HOURLY_NIGHT_INTERVAL),
                "alerts_day": str(DEFAULT_ALERTS_DAY_INTERVAL),
                "alerts_night": str(DEFAULT_ALERTS_NIGHT_INTERVAL),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GoogleWeatherOptionsFlowHandler:
        """Get the options flow for this handler."""
        return GoogleWeatherOptionsFlowHandler(config_entry)


class GoogleWeatherOptionsFlowHandler(config_entries.OptionsFlow):
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
            elif not (-180 <= longitude <= 180):
                errors[CONF_LONGITUDE] = "invalid_longitude"
            else:
                # Update coordinator with new values
                return self.async_create_entry(title="", data=user_input)

        # Get current values from config or options
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
                    # Current conditions intervals
                    vol.Optional(
                        CONF_CURRENT_DAY_INTERVAL,
                        default=current_data.get(CONF_CURRENT_DAY_INTERVAL, DEFAULT_CURRENT_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_CURRENT_NIGHT_INTERVAL,
                        default=current_data.get(CONF_CURRENT_NIGHT_INTERVAL, DEFAULT_CURRENT_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Daily forecast intervals
                    vol.Optional(
                        CONF_DAILY_DAY_INTERVAL,
                        default=current_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_DAILY_NIGHT_INTERVAL,
                        default=current_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Hourly forecast intervals
                    vol.Optional(
                        CONF_HOURLY_DAY_INTERVAL,
                        default=current_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_HOURLY_NIGHT_INTERVAL,
                        default=current_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Weather alerts intervals
                    vol.Optional(
                        CONF_ALERTS_DAY_INTERVAL,
                        default=current_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(
                        CONF_ALERTS_NIGHT_INTERVAL,
                        default=current_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    # Night time period
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
