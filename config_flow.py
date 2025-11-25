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
    CONF_LOCATION,
    CONF_PREFIX,
    DEFAULT_PREFIX,
    DOMAIN,
    OAUTH2_SCOPES,
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

                return self.async_create_entry(
                    title=f"Google Weather - {location_name}",
                    data={
                        **self.oauth_data,
                        CONF_LOCATION: location_name,
                        CONF_PREFIX: prefix,
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                    },
                )

        # Default to Home Assistant's configured location
        default_latitude = self.hass.config.latitude
        default_longitude = self.hass.config.longitude

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION, default="Home"): str,
                    vol.Optional(CONF_PREFIX, default=DEFAULT_PREFIX): str,
                    vol.Required(CONF_LATITUDE, default=default_latitude): vol.Coerce(float),
                    vol.Required(CONF_LONGITUDE, default=default_longitude): vol.Coerce(float),
                }
            ),
            errors=errors,
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
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOCATION,
                        default=self.config_entry.data.get(CONF_LOCATION, "Home"),
                    ): str,
                    vol.Required(
                        CONF_PREFIX,
                        default=self.config_entry.data.get(CONF_PREFIX, DEFAULT_PREFIX),
                    ): str,
                    vol.Required(
                        CONF_LATITUDE,
                        default=self.config_entry.data.get(CONF_LATITUDE),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_LONGITUDE,
                        default=self.config_entry.data.get(CONF_LONGITUDE),
                    ): vol.Coerce(float),
                }
            ),
        )
