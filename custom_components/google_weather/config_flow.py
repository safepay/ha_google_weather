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
from . import nowcast
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
    CONF_INCLUDE_MINUTE_FORECAST,
    CONF_LOCATION,
    CONF_MINUTE_MIN_INTERVAL,
    CONF_MINUTE_MONTHLY_BUDGET,
    CONF_MINUTE_RAIN_THRESHOLD,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
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
    DEFAULT_INCLUDE_MINUTE_FORECAST,
    DEFAULT_MINUTE_MIN_INTERVAL,
    DEFAULT_MINUTE_MONTHLY_BUDGET,
    DEFAULT_MINUTE_RAIN_THRESHOLD,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DOMAIN,
    MINUTE_MIN_INTERVAL_LABELS,
    MINUTE_MIN_INTERVAL_OPTIONS,
    MINUTE_PROBE_PAGE_SIZE,
    API_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


def _calculate_monthly_calls(
    day_interval: int, night_interval: int, day_hours: int = 16, night_hours: int = 8
) -> int:
    """Calculate monthly API calls for an endpoint."""
    days_per_month = 30
    calls_per_hour_day = 60 / day_interval
    calls_per_hour_night = 60 / night_interval

    day_calls = calls_per_hour_day * day_hours * days_per_month
    night_calls = calls_per_hour_night * night_hours * days_per_month

    return int(day_calls + night_calls)


# Simulated: ten rain days of four hours each, at each selectable interval. This
# is the "10 rain days" row of the table in const.py next to
# MINUTE_MIN_INTERVAL_OPTIONS, and has to be changed with it.
_MINUTE_TEMPERATE_ESTIMATE = {2: 1480, 3: 1080, 5: 750, 10: 500, 15: 410}


def _estimate_minute_calls(min_interval: int) -> int:
    """Monthly nowcast calls in a temperate climate at this minimum interval."""
    return _MINUTE_TEMPERATE_ESTIMATE.get(
        min_interval, _MINUTE_TEMPERATE_ESTIMATE[DEFAULT_MINUTE_MIN_INTERVAL]
    )


def _probe_minute_cadence(
    api_key: str, latitude: float, longitude: float
) -> float | None:
    """Learn this location's segment width with one small call.

    Segment width varies by location and nothing but a response reveals it, so
    it is read rather than predicted. Returns None on any failure: the endpoint
    is pre-GA and must never block setup.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/forecast/minutes:lookup",
            params={
                "key": api_key,
                "location.latitude": latitude,
                "location.longitude": longitude,
                "pageSize": MINUTE_PROBE_PAGE_SIZE,
            },
            timeout=10,
        )
        response.raise_for_status()
        segments = nowcast.parse_segments(response.json())
    except (requests.RequestException, ValueError) as err:
        _LOGGER.debug("Minute forecast probe failed: %s", err)
        return None

    if not segments:
        _LOGGER.debug("Minute forecast probe returned no usable segments")
        return None

    # The narrowest segment, not the first: a response that leads with a
    # multi-hour block would otherwise be measured as hours wide.
    return min(segment.duration_minutes for segment in segments)


def _default_min_interval(cadence: float | None) -> int:
    """Pick the interval default for a location of this segment width.

    Never faster than the data changes shape, and never below the cost-balanced
    default - so a two-minute region keeps 5 rather than dropping to 2.
    """
    if not cadence:
        return DEFAULT_MINUTE_MIN_INTERVAL
    matched = next(
        (option for option in MINUTE_MIN_INTERVAL_OPTIONS if option >= cadence),
        MINUTE_MIN_INTERVAL_OPTIONS[-1],
    )
    return max(DEFAULT_MINUTE_MIN_INTERVAL, matched)


def _interval_choices(cadence: float | None) -> dict[str, str]:
    """The intervals worth offering for a location of this segment width.

    Polling faster than the segments are wide costs calls for no finer an
    answer, so those options are not offered at all rather than left in the list
    to be regretted. An unmeasured width offers everything.

    Keyed by string, because a form schema reaches the frontend as JSON and
    object keys are strings there. An integer default against string options
    matches nothing and the field renders with no selection.
    """
    options = [
        option
        for option in MINUTE_MIN_INTERVAL_OPTIONS
        if not cadence or option >= cadence
    ]
    if not options:
        # Segments wider than anything on the ladder: the coarsest is the best
        # available match.
        options = [MINUTE_MIN_INTERVAL_OPTIONS[-1]]

    if len(options) == 1 and cadence:
        width = int(round(cadence))
        return {
            str(options[0]): f"{options[0]} minutes - matches this location's "
                             f"{width}-minute segments"
        }

    return {str(option): MINUTE_MIN_INTERVAL_LABELS[option] for option in options}


def _coerce_min_interval(user_input: dict[str, Any]) -> dict[str, Any]:
    """Store the polling interval as a number, whatever the form returned.

    The select hands back a string, and everything downstream does arithmetic
    with it.
    """
    if CONF_MINUTE_MIN_INTERVAL not in user_input:
        return user_input
    data = dict(user_input)
    try:
        data[CONF_MINUTE_MIN_INTERVAL] = int(data[CONF_MINUTE_MIN_INTERVAL])
    except (TypeError, ValueError):
        data[CONF_MINUTE_MIN_INTERVAL] = DEFAULT_MINUTE_MIN_INTERVAL
    return data


def _clamp_to_choices(stored: int, cadence: float | None) -> str:
    """Keep a stored interval selectable after the measured width coarsens.

    A location that used to return fine segments may stop doing so, and a stored
    value no longer on the list would render unselected and fail validation.
    """
    if str(stored) in _interval_choices(cadence):
        return str(stored)
    return str(_default_min_interval(cadence))


def _cadence_note(cadence: float | None, enabled: bool) -> str:
    """A line for the intervals step saying what this location actually returns."""
    if not enabled:
        return ""
    if not cadence:
        return (
            "\n\nThe minute forecast's segment width could not be read for this "
            "location. It will be shown here once a forecast has been fetched."
        )
    width = int(round(cadence))
    note = f"\n\nThis location returns {width}-minute minute-forecast segments."
    if len(_interval_choices(cadence)) < len(MINUTE_MIN_INTERVAL_OPTIONS):
        note += (
            " Shorter intervals are not offered: calling more often than the "
            "forecast changes would cost calls without giving a finer answer."
        )
    return note


def _describe_cadence(cadence: float | None, min_interval: int) -> str:
    """Explain what segment width this location returns, if it is known yet.

    Segment width is set by Google, varies by location and is not a setting.
    Polling faster than it still gets revisions sooner, but no finer an answer,
    so say so rather than let the interval choice imply detail that is not there.
    """
    if not cadence:
        return (
            "\n\u2139\ufe0f This location's segment width is not known yet. Polling "
            "faster than it gets revisions sooner but no finer an answer.\n"
        )

    width = int(round(cadence))
    note = f"\n\u2139\ufe0f This location returns {width}-minute segments.\n"
    if min_interval < width:
        note += (
            f"Polling every {min_interval} minutes is faster than the data "
            f"changes shape. You will hear about revisions sooner, but onset "
            f"times still move in {width}-minute steps. Consider {width} "
            f"minutes unless you want the earlier warning.\n"
        )
    return note


def _build_usage_description(
    forecast_data: dict[str, Any],
    interval_data: dict[str, Any],
    cadence: float | None = None,
) -> str:
    """Build API usage description string from forecast and interval data."""
    current_calls = _calculate_monthly_calls(
        interval_data[CONF_CURRENT_DAY_INTERVAL],
        interval_data[CONF_CURRENT_NIGHT_INTERVAL],
    )

    daily_calls = _calculate_monthly_calls(
        interval_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
        interval_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
    )

    hourly_calls = 0
    if forecast_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
        hourly_calls = _calculate_monthly_calls(
            interval_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
            interval_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
        )

    alerts_calls = 0
    if forecast_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
        alerts_calls = _calculate_monthly_calls(
            interval_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
            interval_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
        )

    # Cannot be worked out in advance: its cost is decided by how much it rains.
    minute_enabled = forecast_data.get(
        CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
    )
    minute_budget = interval_data.get(
        CONF_MINUTE_MONTHLY_BUDGET, DEFAULT_MINUTE_MONTHLY_BUDGET
    )
    # The nowcast is excluded: folding a guess into a figure presented as a
    # calculation would be misleading. It is called out separately below.
    total_calls = current_calls + daily_calls + hourly_calls + alerts_calls
    headroom = 10000 - total_calls
    headroom_pct = (headroom / 10000) * 100

    status = "\u2705" if total_calls <= 10000 else "\u274c"

    daily_line = f"\u2022 Daily Forecast: ~{daily_calls:,} calls/month\n"

    if forecast_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
        hourly_line = f"\u2022 Hourly Forecast: ~{hourly_calls:,} calls/month\n"
    else:
        hourly_line = "\u2022 Hourly Forecast: 0 calls/month (disabled)\n"

    if forecast_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
        alerts_line = f"\u2022 Weather Alerts: ~{alerts_calls:,} calls/month\n"
    else:
        alerts_line = "\u2022 Weather Alerts: 0 calls/month (disabled)\n"

    if minute_enabled:
        minute_interval = interval_data.get(
            CONF_MINUTE_MIN_INTERVAL, DEFAULT_MINUTE_MIN_INTERVAL
        )
        minute_line = (
            f"\u2022 Minute Forecast (alpha): depends on the weather \u2014 ~120/month if dry, "
            f"~{_estimate_minute_calls(minute_interval):,} temperate, more if wet\n"
        )
    else:
        minute_line = "\u2022 Minute Forecast: 0 calls/month (disabled)\n"

    description = (
        f"**Estimated Monthly API Usage:**\n\n"
        f"\u2022 Current Conditions: ~{current_calls:,} calls/month\n"
        f"{daily_line}"
        f"{hourly_line}"
        f"{alerts_line}"
        f"{minute_line}\n"
        f"**Total: ~{total_calls:,} calls/month** {status}\n"
        f"Free tier limit: 10,000 calls/month\n"
    )

    if total_calls <= 10000:
        description += f"Headroom: {headroom:,} calls ({headroom_pct:.1f}% buffer)\n\n\u2705 Within free tier limits"
    else:
        excess = total_calls - 10000
        description += f"\n\u26a0\ufe0f **Warning:** Exceeds free tier by {excess:,} calls/month\n"
        description += "Consider reducing update intervals or expect charges."

    if minute_enabled:
        description += (
            f"\n\n---\n"
            f"\u26a0\ufe0f **The minute forecast can take you over the 10,000 free calls.**\n\n"
            f"Its cost depends on the weather, so it is not included above. You have "
            f"{headroom:,} calls of headroom.\n\n"
            f"The ceiling of {minute_budget:,} slows polling to two-hourly, but it is "
            f"not a guarantee: it resets when Home Assistant restarts and cannot see "
            f"other users of your API key.\n\n"
            f"Set a quota cap in the Google Cloud console if staying free matters.\n"
            + _describe_cadence(cadence, minute_interval)
        )

    description += "\n\n---\n**Ready to proceed?** Click **Next** to complete setup."

    return description


class GoogleWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self.api_key: str | None = None
        self.user_data: dict[str, Any] = {}
        self.forecast_data: dict[str, Any] = {}
        self.interval_data: dict[str, Any] = {}
        self.minute_cadence: float | None = None

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
                }
                return await self.async_step_forecasts()

        # Default to Home Assistant's configured location
        default_latitude = self.hass.config.latitude
        default_longitude = self.hass.config.longitude
        default_location_name = self.hass.config.location_name or "home"

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION, default=default_location_name): str,
                    vol.Required(CONF_LATITUDE, default=default_latitude): vol.Coerce(float),
                    vol.Required(CONF_LONGITUDE, default=default_longitude): vol.Coerce(float),
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
                CONF_INCLUDE_MINUTE_FORECAST: user_input.get(
                    CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
                ),
            }
            if self.forecast_data[CONF_INCLUDE_MINUTE_FORECAST]:
                # One call, so the interval step can offer a default that suits
                # this region rather than warning about it afterwards.
                self.minute_cadence = await self.hass.async_add_executor_job(
                    _probe_minute_cadence,
                    self.api_key,
                    self.user_data[CONF_LATITUDE],
                    self.user_data[CONF_LONGITUDE],
                )
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
                    vol.Optional(
                        CONF_INCLUDE_MINUTE_FORECAST,
                        default=DEFAULT_INCLUDE_MINUTE_FORECAST,
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
            self.interval_data = _coerce_min_interval(user_input)
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

        # Self-scheduling, so no day/night pair: a floor, a gate and a ceiling.
        if self.forecast_data.get(CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST):
            schema_dict.update({
                # Required so the default renders selected: an Optional select
                # is drawn with nothing chosen.
                vol.Required(
                    CONF_MINUTE_MIN_INTERVAL,
                    default=str(_default_min_interval(self.minute_cadence)),
                ): vol.In(_interval_choices(self.minute_cadence)),
                vol.Optional(
                    CONF_MINUTE_RAIN_THRESHOLD,
                    default=DEFAULT_MINUTE_RAIN_THRESHOLD,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_MINUTE_MONTHLY_BUDGET,
                    default=DEFAULT_MINUTE_MONTHLY_BUDGET,
                ): vol.All(vol.Coerce(int), vol.Range(min=100, max=10000)),
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
            description_placeholders={
                "minute_note": _cadence_note(
                    self.minute_cadence,
                    self.forecast_data.get(
                        CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
                    ),
                )
            },
        )

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

        description = _build_usage_description(
            self.forecast_data, self.interval_data, self.minute_cadence
        )

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
        self.location_data: dict[str, Any] = {}
        self.forecast_options: dict[str, Any] = {}
        self.interval_data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage location and forecast options."""
        errors = {}

        # Get current values from config_entry (data or options)
        current_data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            # Validate latitude and longitude
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if not (-90 <= latitude <= 90):
                errors[CONF_LATITUDE] = "invalid_latitude"
            if not (-180 <= longitude <= 180):
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                # Store location and forecast options
                self.location_data = {
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                }
                # Daily forecasts are always enabled (not configurable)
                self.forecast_options = {
                    CONF_INCLUDE_DAILY_FORECAST: True,  # Always enabled
                    CONF_INCLUDE_HOURLY_FORECAST: user_input.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST),
                    CONF_INCLUDE_ALERTS: user_input.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS),
                    CONF_INCLUDE_MINUTE_FORECAST: user_input.get(
                        CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
                    ),
                }
                return await self.async_step_intervals()

        # Build schema for location and forecast checkboxes
        schema_dict = {
            vol.Required(
                CONF_LATITUDE,
                default=current_data.get(CONF_LATITUDE),
            ): vol.Coerce(float),
            vol.Required(
                CONF_LONGITUDE,
                default=current_data.get(CONF_LONGITUDE),
            ): vol.Coerce(float),
            # Hourly forecast checkbox
            vol.Optional(
                CONF_INCLUDE_HOURLY_FORECAST,
                default=current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST),
            ): bool,
            # Weather alerts checkbox (always shown - no entities created if not supported)
            vol.Optional(
                CONF_INCLUDE_ALERTS,
                default=current_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS),
            ): bool,
            # Minute forecast checkbox (alpha, off by default)
            vol.Optional(
                CONF_INCLUDE_MINUTE_FORECAST,
                default=current_data.get(
                    CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
                ),
            ): bool,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_intervals(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure update intervals for API endpoints."""
        if user_input is not None:
            # Store interval data and show confirmation
            self.interval_data = _coerce_min_interval(user_input)
            return await self.async_step_confirm()

        # Get current values from config_entry (data or options)
        current_data = {**self.config_entry.data, **self.config_entry.options}

        # Build schema based on selected forecasts
        schema_dict = {
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

        # Add hourly forecast intervals if enabled
        if self.forecast_options.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
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

        # Add weather alerts intervals if enabled
        if self.forecast_options.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS):
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

        # Minute forecast settings, shown only when enabled.
        if self.forecast_options.get(CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST):
            schema_dict.update({
                vol.Required(
                    CONF_MINUTE_MIN_INTERVAL,
                    default=_clamp_to_choices(
                        current_data.get(CONF_MINUTE_MIN_INTERVAL, DEFAULT_MINUTE_MIN_INTERVAL),
                        self._observed_cadence(),
                    ),
                ): vol.In(_interval_choices(self._observed_cadence())),
                vol.Optional(
                    CONF_MINUTE_RAIN_THRESHOLD,
                    default=current_data.get(CONF_MINUTE_RAIN_THRESHOLD, DEFAULT_MINUTE_RAIN_THRESHOLD),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_MINUTE_MONTHLY_BUDGET,
                    default=current_data.get(CONF_MINUTE_MONTHLY_BUDGET, DEFAULT_MINUTE_MONTHLY_BUDGET),
                ): vol.All(vol.Coerce(int), vol.Range(min=100, max=10000)),
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
            step_id="intervals",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "minute_note": _cadence_note(
                    self._observed_cadence(),
                    self.forecast_options.get(
                        CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
                    ),
                )
            },
        )

    def _observed_cadence(self) -> float | None:
        """Segment width from the last nowcast response, if one has arrived."""
        coordinator = (self.hass.data.get(DOMAIN) or {}).get(self.config_entry.entry_id)
        endpoint_data = getattr(coordinator, "endpoint_data", None) or {}
        return (endpoint_data.get("minute_forecast") or {}).get("cadence_minutes")

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show confirmation with API usage calculation."""
        if user_input is not None:
            # User confirmed, merge all data and update the options
            final_data = {
                **self.location_data,
                **self.forecast_options,
                **self.interval_data,
            }
            return self.async_create_entry(title="", data=final_data)

        description = _build_usage_description(
            self.forecast_options, self.interval_data, self._observed_cadence()
        )

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"usage_summary": description},
            data_schema=vol.Schema({}),
            last_step=False,
        )
