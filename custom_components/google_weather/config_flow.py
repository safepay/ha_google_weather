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
from homeassistant.util.unit_system import METRIC_SYSTEM

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
    CONF_INCLUDE_ALERTS,
    CONF_INCLUDE_DAILY_FORECAST,
    CONF_INCLUDE_HOURLY_FORECAST,
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
    DEFAULT_INCLUDE_ALERTS,
    DEFAULT_INCLUDE_DAILY_FORECAST,
    DEFAULT_INCLUDE_HOURLY_FORECAST,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_UNIT_SYSTEM,
    DOMAIN,
    API_BASE_URL,
    UNIT_SYSTEMS,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_IMPERIAL,
)

_LOGGER = logging.getLogger(__name__)


class GoogleWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self.api_key: str | None = None
        self.user_data: dict[str, Any] = {}
        self.forecast_data: dict[str, Any] = {}
        self.interval_data: dict[str, Any] = {}

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
                return await self.async_step_forecasts()

        # Default to Home Assistant's configured location
        default_latitude = self.hass.config.latitude
        default_longitude = self.hass.config.longitude
        default_location_name = self.hass.config.location_name or "home"

        # Determine default unit system from Home Assistant configuration
        # Use instance check (is_metric is deprecated since HA 2022.11)
        default_unit_system = UNIT_SYSTEM_METRIC if self.hass.config.units is METRIC_SYSTEM else UNIT_SYSTEM_IMPERIAL

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION, default=default_location_name): str,
                    vol.Required(CONF_LATITUDE, default=default_latitude): vol.Coerce(float),
                    vol.Required(CONF_LONGITUDE, default=default_longitude): vol.Coerce(float),
                    vol.Required(CONF_UNIT_SYSTEM, default=default_unit_system): vol.In(UNIT_SYSTEMS),
                }
            ),
            errors=errors,
        )

    async def async_step_forecasts(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure which forecasts and alerts to include."""
        if user_input is not None:
            # Store forecast selection data
            # Daily forecasts are always enabled (not configurable)
            self.forecast_data = {
                CONF_INCLUDE_DAILY_FORECAST: True,  # Always enabled
                CONF_INCLUDE_HOURLY_FORECAST: user_input.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST),
                CONF_INCLUDE_ALERTS: user_input.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS),
            }
            return await self.async_step_intervals()

        return self.async_show_form(
            step_id="forecasts",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_HOURLY_FORECAST,
                        default=DEFAULT_INCLUDE_HOURLY_FORECAST,
                    ): bool,
                    vol.Optional(
                        CONF_INCLUDE_ALERTS,
                        default=DEFAULT_INCLUDE_ALERTS,
                    ): bool,
                }
            ),
        )

    async def async_step_intervals(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure update intervals for API endpoints."""
        if user_input is not None:
            # Store interval data and show confirmation
            self.interval_data = user_input
            return await self.async_step_confirm()

        # Build schema based on selected forecasts
        schema_dict = {
            # Current conditions intervals (always shown)
            vol.Optional(
                CONF_CURRENT_DAY_INTERVAL,
                default=DEFAULT_CURRENT_DAY_INTERVAL,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional(
                CONF_CURRENT_NIGHT_INTERVAL,
                default=DEFAULT_CURRENT_NIGHT_INTERVAL,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            # Daily forecast intervals (always shown - daily forecasts are always enabled)
            vol.Optional(
                CONF_DAILY_DAY_INTERVAL,
                default=DEFAULT_DAILY_DAY_INTERVAL,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional(
                CONF_DAILY_NIGHT_INTERVAL,
                default=DEFAULT_DAILY_NIGHT_INTERVAL,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        }

        # Add hourly forecast intervals if enabled
        if self.forecast_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            schema_dict.update({
                vol.Optional(
                    CONF_HOURLY_DAY_INTERVAL,
                    default=DEFAULT_HOURLY_DAY_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Optional(
                    CONF_HOURLY_NIGHT_INTERVAL,
                    default=DEFAULT_HOURLY_NIGHT_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            })

        # Add weather alerts intervals if enabled
        if self.forecast_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            schema_dict.update({
                vol.Optional(
                    CONF_ALERTS_DAY_INTERVAL,
                    default=DEFAULT_ALERTS_DAY_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Optional(
                    CONF_ALERTS_NIGHT_INTERVAL,
                    default=DEFAULT_ALERTS_NIGHT_INTERVAL,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            })

        # Night time period (always shown)
        schema_dict.update({
            vol.Optional(
                CONF_NIGHT_START,
                default=DEFAULT_NIGHT_START,
            ): str,
            vol.Optional(
                CONF_NIGHT_END,
                default=DEFAULT_NIGHT_END,
            ): str,
        })

        return self.async_show_form(
            step_id="intervals",
            data_schema=vol.Schema(schema_dict),
        )

    def _calculate_monthly_calls(
        self, day_interval: int, night_interval: int, day_hours: int = 16, night_hours: int = 8
    ) -> int:
        """Calculate monthly API calls for an endpoint."""
        days_per_month = 30
        calls_per_hour_day = 60 / day_interval
        calls_per_hour_night = 60 / night_interval

        day_calls = calls_per_hour_day * day_hours * days_per_month
        night_calls = calls_per_hour_night * night_hours * days_per_month

        return int(day_calls + night_calls)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show confirmation with API usage calculation."""
        if user_input is not None:
            # User confirmed, create the entry
            final_data = {
                CONF_API_KEY: self.api_key,
                **self.user_data,
                **self.forecast_data,
                **self.interval_data,
            }

            location_name = self.user_data[CONF_LOCATION]
            return self.async_create_entry(
                title=f"Google Weather - {location_name}",
                data=final_data,
            )

        # Calculate API usage for each endpoint
        current_calls = self._calculate_monthly_calls(
            self.interval_data[CONF_CURRENT_DAY_INTERVAL],
            self.interval_data[CONF_CURRENT_NIGHT_INTERVAL],
        )

        # Daily forecast calls (always enabled)
        daily_calls = self._calculate_monthly_calls(
            self.interval_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
            self.interval_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
        )

        # Only calculate hourly forecast calls if enabled
        hourly_calls = 0
        if self.forecast_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            hourly_calls = self._calculate_monthly_calls(
                self.interval_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                self.interval_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
            )

        # Only calculate alerts calls if enabled
        alerts_calls = 0
        if self.forecast_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            alerts_calls = self._calculate_monthly_calls(
                self.interval_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                self.interval_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
            )

        total_calls = current_calls + daily_calls + hourly_calls + alerts_calls
        headroom = 10000 - total_calls
        headroom_pct = (headroom / 10000) * 100

        # Build description with calculation results
        status = "✅" if total_calls <= 10000 else "❌"

        # Daily forecast is always enabled
        daily_line = f"• Daily Forecast: ~{daily_calls:,} calls/month\n"

        # Format hourly forecast line
        if self.forecast_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            hourly_line = f"• Hourly Forecast: ~{hourly_calls:,} calls/month\n"
        else:
            hourly_line = "• Hourly Forecast: 0 calls/month (disabled)\n"

        # Format alerts line
        if self.forecast_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            alerts_line = f"• Weather Alerts: ~{alerts_calls:,} calls/month\n"
        else:
            alerts_line = "• Weather Alerts: 0 calls/month (disabled)\n"

        description = (
            f"**Estimated Monthly API Usage:**\n\n"
            f"• Current Conditions: ~{current_calls:,} calls/month\n"
            f"{daily_line}"
            f"{hourly_line}"
            f"{alerts_line}\n"
            f"**Total: ~{total_calls:,} calls/month** {status}\n"
            f"Free tier limit: 10,000 calls/month\n"
        )

        if total_calls <= 10000:
            description += f"Headroom: {headroom:,} calls ({headroom_pct:.1f}% buffer)\n\n✅ Within free tier limits"
        else:
            excess = total_calls - 10000
            description += f"\n⚠️ **Warning:** Exceeds free tier by {excess:,} calls/month\n"
            description += "Consider reducing update intervals or expect charges."

        description += "\n\n---\n**Ready to proceed?** Click **Next** to complete setup."

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"usage_summary": description},
            data_schema=vol.Schema({}),
            last_step=False,
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
        super().__init__()
        self.options_data: dict[str, Any] = {}
        self.forecast_options: dict[str, Any] = {}

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
                # Store options data and forecast options separately
                # Daily forecasts are always enabled (not configurable)
                self.options_data = user_input
                self.forecast_options = {
                    CONF_INCLUDE_DAILY_FORECAST: True,  # Always enabled
                    CONF_INCLUDE_HOURLY_FORECAST: user_input.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST),
                    CONF_INCLUDE_ALERTS: user_input.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS),
                }
                return await self.async_step_confirm()

        # Get current values from config_entry (data or options)
        current_data = {**self.config_entry.data, **self.config_entry.options}

        # Check if coordinator has been created and if alerts are supported
        coordinator = None
        alerts_supported = True  # Default to True (show option) if we can't determine
        try:
            coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
            if coordinator and hasattr(coordinator, 'alerts_supported'):
                # If alerts_supported is False, don't show the option
                alerts_supported = coordinator.alerts_supported is not False
        except Exception:
            pass  # If we can't get coordinator, default to showing alerts option

        # Build schema based on current forecast settings
        schema_dict = {
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
            # Forecast inclusion options (daily is always enabled, not shown)
            vol.Optional(
                CONF_INCLUDE_HOURLY_FORECAST,
                default=current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST),
            ): bool,
            # Current conditions intervals (always shown)
            vol.Optional(
                CONF_CURRENT_DAY_INTERVAL,
                default=current_data.get(CONF_CURRENT_DAY_INTERVAL, DEFAULT_CURRENT_DAY_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional(
                CONF_CURRENT_NIGHT_INTERVAL,
                default=current_data.get(CONF_CURRENT_NIGHT_INTERVAL, DEFAULT_CURRENT_NIGHT_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            # Daily forecast intervals (always shown - daily forecasts are always enabled)
            vol.Optional(
                CONF_DAILY_DAY_INTERVAL,
                default=current_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional(
                CONF_DAILY_NIGHT_INTERVAL,
                default=current_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        }

        # Add weather alerts checkbox only if alerts are supported for this location
        if alerts_supported:
            schema_dict[vol.Optional(
                CONF_INCLUDE_ALERTS,
                default=current_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS),
            )] = bool

        # Add hourly forecast intervals if currently enabled
        if current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            schema_dict.update({
                vol.Optional(
                    CONF_HOURLY_DAY_INTERVAL,
                    default=current_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Optional(
                    CONF_HOURLY_NIGHT_INTERVAL,
                    default=current_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            })

        # Add weather alerts intervals if currently enabled AND supported
        if alerts_supported and current_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            schema_dict.update({
                vol.Optional(
                    CONF_ALERTS_DAY_INTERVAL,
                    default=current_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Optional(
                    CONF_ALERTS_NIGHT_INTERVAL,
                    default=current_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            })

        # Night time period (always shown)
        schema_dict.update({
            vol.Optional(
                CONF_NIGHT_START,
                default=current_data.get(CONF_NIGHT_START, DEFAULT_NIGHT_START),
            ): str,
            vol.Optional(
                CONF_NIGHT_END,
                default=current_data.get(CONF_NIGHT_END, DEFAULT_NIGHT_END),
            ): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    def _calculate_monthly_calls(
        self, day_interval: int, night_interval: int, day_hours: int = 16, night_hours: int = 8
    ) -> int:
        """Calculate monthly API calls for an endpoint."""
        days_per_month = 30
        calls_per_hour_day = 60 / day_interval
        calls_per_hour_night = 60 / night_interval

        day_calls = calls_per_hour_day * day_hours * days_per_month
        night_calls = calls_per_hour_night * night_hours * days_per_month

        return int(day_calls + night_calls)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show confirmation with API usage calculation."""
        if user_input is not None:
            # User confirmed, update the options
            return self.async_create_entry(title="", data=self.options_data)

        # Calculate API usage for each endpoint
        current_calls = self._calculate_monthly_calls(
            self.options_data[CONF_CURRENT_DAY_INTERVAL],
            self.options_data[CONF_CURRENT_NIGHT_INTERVAL],
        )

        # Daily forecast calls (always enabled)
        daily_calls = self._calculate_monthly_calls(
            self.options_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
            self.options_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
        )

        # Only calculate hourly forecast calls if enabled
        hourly_calls = 0
        if self.forecast_options.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            hourly_calls = self._calculate_monthly_calls(
                self.options_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                self.options_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
            )

        # Only calculate alerts calls if enabled
        alerts_calls = 0
        if self.forecast_options.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            alerts_calls = self._calculate_monthly_calls(
                self.options_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                self.options_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
            )

        total_calls = current_calls + daily_calls + hourly_calls + alerts_calls
        headroom = 10000 - total_calls
        headroom_pct = (headroom / 10000) * 100

        # Build description with calculation results
        status = "✅" if total_calls <= 10000 else "❌"

        # Daily forecast is always enabled
        daily_line = f"• Daily Forecast: ~{daily_calls:,} calls/month\n"

        # Format hourly forecast line
        if self.forecast_options.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            hourly_line = f"• Hourly Forecast: ~{hourly_calls:,} calls/month\n"
        else:
            hourly_line = "• Hourly Forecast: 0 calls/month (disabled)\n"

        # Format alerts line
        if self.forecast_options.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
            alerts_line = f"• Weather Alerts: ~{alerts_calls:,} calls/month\n"
        else:
            alerts_line = "• Weather Alerts: 0 calls/month (disabled)\n"

        description = (
            f"**Estimated Monthly API Usage:**\n\n"
            f"• Current Conditions: ~{current_calls:,} calls/month\n"
            f"{daily_line}"
            f"{hourly_line}"
            f"{alerts_line}\n"
            f"**Total: ~{total_calls:,} calls/month** {status}\n"
            f"Free tier limit: 10,000 calls/month\n"
        )

        if total_calls <= 10000:
            description += f"Headroom: {headroom:,} calls ({headroom_pct:.1f}% buffer)\n\n✅ Within free tier limits"
        else:
            excess = total_calls - 10000
            description += f"\n⚠️ **Warning:** Exceeds free tier by {excess:,} calls/month\n"
            description += "Consider reducing update intervals or expect charges."

        description += "\n\n---\n**Ready to proceed?** Click **Next** to complete setup."

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"usage_summary": description},
            data_schema=vol.Schema({}),
            last_step=False,
        )
