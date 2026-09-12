"""Data coordinator for Google Weather integration."""
from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
import logging
from typing import Any
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM

from . import nowcast
from .conditions import SNOW_CONDITION_TYPES
from .const import (
    API_BASE_URL,
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
    ENDPOINT_ALERTS,
    ENDPOINT_CURRENT,
    ENDPOINT_DAILY,
    ENDPOINT_HOURLY,
    ENDPOINT_MINUTE,
    MINUTE_CAP_RELAXED,
    MINUTE_PAGE_SIZE,
    UNIT_SYSTEM_IMPERIAL,
    UNIT_SYSTEM_METRIC,
)

_LOGGER = logging.getLogger(__name__)


def _is_snow_condition(condition: str | None) -> bool:
    """Return True if condition string represents snow."""
    if not condition:
        return False
    return condition.upper() in SNOW_CONDITION_TYPES


def _extract_hourly_snow_amount(hour: dict[str, Any]) -> float | None:
    """Extract per-hour snow amount using precipitation hints."""
    precipitation = hour.get("precipitation") or {}

    snow_amount = (precipitation.get("snowQpf") or {}).get("quantity")
    if snow_amount is None:
        snow_amount = (precipitation.get("snowfallAmount") or {}).get("quantity")

    if snow_amount is None:
        precip_type = precipitation.get("type") or (precipitation.get("probability") or {}).get("type")
        condition_type = hour.get("weatherCondition", {}).get("type")
        if _is_snow_condition(precip_type) or _is_snow_condition(condition_type):
            snow_amount = (precipitation.get("qpf") or {}).get("quantity")

    if snow_amount is None:
        return None

    try:
        return float(snow_amount)
    except (TypeError, ValueError):
        return None


def _calculate_snow_forecast_next_24h(hourly_forecast: list[dict[str, Any]]) -> float | None:
    """Calculate total snow expected over the next 24 hours."""
    if not hourly_forecast:
        return None

    now = dt_util.utcnow()
    cutoff = now + timedelta(hours=24)
    total_snow = 0.0
    contributing_hours = 0
    window_hours = 0

    for hour in hourly_forecast:
        interval = hour.get("interval", {})
        start_time = interval.get("startTime")
        if not start_time:
            continue

        dt = dt_util.parse_datetime(start_time)
        if not dt:
            continue

        forecast_time = dt_util.as_utc(dt)
        if forecast_time < now or forecast_time >= cutoff:
            continue

        window_hours += 1
        snow_amount = _extract_hourly_snow_amount(hour)
        if snow_amount is None:
            continue

        contributing_hours += 1
        total_snow += snow_amount

    if contributing_hours == 0:
        _LOGGER.debug(
            "Snow forecast (24h): no qualifying hourly entries (window=%d, total_entries=%d)",
            window_hours,
            len(hourly_forecast),
        )
        return None

    total_snow = round(total_snow, 3)
    _LOGGER.debug(
        "Snow forecast (24h): total %.3f from %d/%d window hours (entries=%d)",
        total_snow,
        contributing_hours,
        window_hours,
        len(hourly_forecast),
    )
    return total_snow


class GoogleWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage Google Weather API calls with smart polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry

        # Get current data from both data and options (options override data)
        current_data = {**entry.data, **entry.options}

        self.api_key = entry.data.get(CONF_API_KEY)
        self.latitude = current_data.get(CONF_LATITUDE)
        self.longitude = current_data.get(CONF_LONGITUDE)

        # Auto-detect unit system from Home Assistant's configuration
        self.unit_system = UNIT_SYSTEM_METRIC if hass.config.units is METRIC_SYSTEM else UNIT_SYSTEM_IMPERIAL

        # Get forecast/alerts inclusion settings
        self.include_daily_forecast = current_data.get(CONF_INCLUDE_DAILY_FORECAST, DEFAULT_INCLUDE_DAILY_FORECAST)
        self.include_hourly_forecast = current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST)
        self.include_alerts = current_data.get(CONF_INCLUDE_ALERTS, DEFAULT_INCLUDE_ALERTS)
        self.include_minute_forecast = current_data.get(
            CONF_INCLUDE_MINUTE_FORECAST, DEFAULT_INCLUDE_MINUTE_FORECAST
        )
        self.minute_rain_threshold = current_data.get(
            CONF_MINUTE_RAIN_THRESHOLD, DEFAULT_MINUTE_RAIN_THRESHOLD
        )
        self.minute_monthly_budget = current_data.get(
            CONF_MINUTE_MONTHLY_BUDGET, DEFAULT_MINUTE_MONTHLY_BUDGET
        )
        self.minute_min_interval = current_data.get(
            CONF_MINUTE_MIN_INTERVAL, DEFAULT_MINUTE_MIN_INTERVAL
        )

        # Get update intervals
        self.intervals = {
            ENDPOINT_CURRENT: {
                "day": current_data.get(CONF_CURRENT_DAY_INTERVAL, DEFAULT_CURRENT_DAY_INTERVAL),
                "night": current_data.get(CONF_CURRENT_NIGHT_INTERVAL, DEFAULT_CURRENT_NIGHT_INTERVAL),
            },
            ENDPOINT_DAILY: {
                "day": current_data.get(CONF_DAILY_DAY_INTERVAL, DEFAULT_DAILY_DAY_INTERVAL),
                "night": current_data.get(CONF_DAILY_NIGHT_INTERVAL, DEFAULT_DAILY_NIGHT_INTERVAL),
            },
            ENDPOINT_HOURLY: {
                "day": current_data.get(CONF_HOURLY_DAY_INTERVAL, DEFAULT_HOURLY_DAY_INTERVAL),
                "night": current_data.get(CONF_HOURLY_NIGHT_INTERVAL, DEFAULT_HOURLY_NIGHT_INTERVAL),
            },
            ENDPOINT_ALERTS: {
                "day": current_data.get(CONF_ALERTS_DAY_INTERVAL, DEFAULT_ALERTS_DAY_INTERVAL),
                "night": current_data.get(CONF_ALERTS_NIGHT_INTERVAL, DEFAULT_ALERTS_NIGHT_INTERVAL),
            },
        }

        # Get night time configuration
        self.night_start = current_data.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)
        self.night_end = current_data.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)

        # Track last update time for each endpoint
        self.last_update: dict[str, datetime | None] = {
            ENDPOINT_CURRENT: None,
            ENDPOINT_DAILY: None,
            ENDPOINT_HOURLY: None,
            ENDPOINT_ALERTS: None,
            ENDPOINT_MINUTE: None,
        }

        # Cache data for each endpoint
        self.endpoint_data: dict[str, Any] = {}

        # Track whether alerts are supported for this location
        self.alerts_supported: bool | None = None  # None = not checked yet

        # The nowcast schedules itself rather than running on a fixed interval,
        # so it carries its own next-call time instead of an entry in intervals.
        self.minute_next_poll: datetime | None = None
        self.minute_failures = 0
        self.minute_cadence: float | None = None
        self.minute_calls = 0
        self.minute_calls_month: tuple[int, int] | None = None

        # Use 1 minute update interval - checks frequently but only fetches when needed
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )

    def _is_night_time(self) -> bool:
        """Check if current time is within night time period."""
        now = dt_util.now().time()

        # Parse time strings
        start_hour, start_min = map(int, self.night_start.split(":"))
        end_hour, end_min = map(int, self.night_end.split(":"))

        start_time = dt_time(start_hour, start_min)
        end_time = dt_time(end_hour, end_min)

        # Handle cases where night period crosses midnight
        if start_time < end_time:
            return start_time <= now < end_time
        else:
            return now >= start_time or now < end_time

    def _should_update_endpoint(self, endpoint: str) -> bool:
        """Check if an endpoint should be updated based on configured intervals."""
        if endpoint == ENDPOINT_MINUTE:
            # Scheduled from the last response, not a day/night pair: calls are
            # only worth making as rain approaches.
            return self.minute_next_poll is None or dt_util.now() >= self.minute_next_poll

        last_update = self.last_update.get(endpoint)

        # If never updated, update now
        if last_update is None:
            return True

        # Get appropriate interval based on time of day
        is_night = self._is_night_time()
        interval_minutes = self.intervals[endpoint]["night" if is_night else "day"]

        # Check if enough time has passed
        time_since_update = (dt_util.now() - last_update).total_seconds() / 60
        return time_since_update >= interval_minutes

    def _schedule_minute_forecast(self, minutes: float, reason: str) -> None:
        """Book the next nowcast call."""
        self.minute_next_poll = dt_util.now() + timedelta(minutes=minutes)
        _LOGGER.debug("Next minute forecast in %d min (%s)", minutes, reason)

    def _count_minute_call(self) -> None:
        """Record a nowcast call against this calendar month's ceiling."""
        now = dt_util.now()
        month = (now.year, now.month)
        if self.minute_calls_month != month:
            self.minute_calls_month = month
            self.minute_calls = 0
        self.minute_calls += 1

    def _minute_budget_exhausted(self) -> bool:
        """Whether this month's nowcast ceiling has been reached."""
        return bool(self.minute_monthly_budget) and self.minute_calls >= self.minute_monthly_budget

    def _apply_minute_schedule(self, updated_data: dict[str, Any]) -> None:
        """Set the next nowcast call from the response just received."""
        if "minute_forecast_error" in updated_data:
            # Escalating backoff, not a capability latch: it slows retries
            # without ever deciding a location is unsupported.
            self.minute_failures = min(self.minute_failures + 1, 8)
            delay = min(
                MINUTE_CAP_RELAXED, self.minute_min_interval * 2**self.minute_failures
            )
            self._schedule_minute_forecast(delay, f"failure {self.minute_failures}")
            return

        derived = updated_data.get("minute_forecast")
        if not derived:
            return

        self.minute_failures = 0

        # Segment width is read, never assumed, and is not stable: say so when it
        # moves, since it changes how precise an answer the entities can give.
        cadence = derived.get("cadence_minutes")
        if cadence and cadence != self.minute_cadence:
            if self.minute_cadence is not None:
                _LOGGER.info(
                    "Minute forecast segment width changed from %s to %s minutes",
                    self.minute_cadence,
                    cadence,
                )
            self.minute_cadence = cadence

        if self._minute_budget_exhausted():
            # Degrade rather than go dark: two-hourly still answers "is rain
            # coming at all".
            self._schedule_minute_forecast(
                MINUTE_CAP_RELAXED,
                f"monthly ceiling reached ({self.minute_calls}/{self.minute_monthly_budget})",
            )
            return

        # Read after the cache update, so the gate sees this tick's forecast when
        # one was fetched alongside.
        outlook = nowcast.forecast_outlook(
            current=self.endpoint_data.get("current"),
            hourly=self.endpoint_data.get("hourly_forecast"),
            daily=self.endpoint_data.get("daily_forecast"),
            now=dt_util.utcnow(),
            is_night=self._is_night_time(),
            threshold=self.minute_rain_threshold,
        )
        delay = nowcast.next_poll_minutes(
            derived, outlook=outlook, floor=self.minute_min_interval
        )
        self._schedule_minute_forecast(
            delay,
            f"onset={derived.get('starts_in')} outlook={outlook} "
            f"calls={self.minute_calls}/{self.minute_monthly_budget}",
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Google Weather API using smart polling."""
        try:
            # Build list of enabled endpoints
            # Current conditions and daily forecasts are always enabled
            enabled_endpoints = [ENDPOINT_CURRENT, ENDPOINT_DAILY]
            if self.include_hourly_forecast:
                enabled_endpoints.append(ENDPOINT_HOURLY)
            if self.include_alerts:
                enabled_endpoints.append(ENDPOINT_ALERTS)
            if self.include_minute_forecast:
                enabled_endpoints.append(ENDPOINT_MINUTE)

            # Check which enabled endpoints need updating
            endpoints_to_update = {
                endpoint: self._should_update_endpoint(endpoint)
                for endpoint in enabled_endpoints
            }

            # If nothing needs updating, return cached data
            if not any(endpoints_to_update.values()):
                _LOGGER.debug("No endpoints need updating, using cached data")
                return self.endpoint_data

            # Log which endpoints are being updated
            updating = [ep for ep, should_update in endpoints_to_update.items() if should_update]
            _LOGGER.debug(
                "Updating endpoints: %s (night mode: %s)",
                ", ".join(updating),
                self._is_night_time(),
            )

            if ENDPOINT_MINUTE in updating:
                # Book before the call, not after: last_update is only stamped on
                # success, so a failing endpoint would otherwise retry every tick.
                self._schedule_minute_forecast(self.minute_min_interval, "attempt booked")

            # Fetch data from endpoints that need updating
            updated_data = await self.hass.async_add_executor_job(
                self._fetch_weather_data,
                endpoints_to_update,
            )

            # Update cache and last update times
            self.endpoint_data.update(updated_data)

            now = dt_util.now()
            for endpoint in updating:
                self.last_update[endpoint] = now

            if ENDPOINT_MINUTE in updating:
                self._apply_minute_schedule(updated_data)

            return self.endpoint_data

        except Exception as err:
            _LOGGER.error("Error fetching weather data: %s", err)
            # Return cached data if available, otherwise raise error
            if self.endpoint_data:
                _LOGGER.warning("Using cached data due to API error")
                return self.endpoint_data
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def _fetch_weather_data(
        self,
        endpoints_to_update: dict[str, bool],
    ) -> dict[str, Any]:
        """Fetch weather data from Google Weather API (runs in executor)."""
        try:
            # Prepare common parameters for weather endpoints (with unitsSystem)
            weather_params = {
                "key": self.api_key,
                "location.latitude": self.latitude,
                "location.longitude": self.longitude,
                "unitsSystem": self.unit_system,
            }

            # Prepare parameters for alerts endpoint (without units_system)
            alerts_params = {
                "key": self.api_key,
                "location.latitude": self.latitude,
                "location.longitude": self.longitude,
            }

            updated_data = {}

            # Fetch current conditions if needed
            if endpoints_to_update.get(ENDPOINT_CURRENT):
                _LOGGER.debug("Fetching current conditions")
                current_response = requests.get(
                    f"{API_BASE_URL}/currentConditions:lookup",
                    params=weather_params,
                    timeout=10,
                )
                current_response.raise_for_status()
                updated_data["current"] = current_response.json()

            # Fetch daily forecast if needed
            if endpoints_to_update.get(ENDPOINT_DAILY):
                _LOGGER.debug("Fetching daily forecast")
                daily_params = {
                    **weather_params,
                    "days": 10,  # Get 10 days of forecast
                    "pageSize": 10,  # Get 10 days in single API request
                }

                daily_response = requests.get(
                    f"{API_BASE_URL}/forecast/days:lookup",
                    params=daily_params,
                    timeout=10,
                )
                daily_response.raise_for_status()
                forecast_data = daily_response.json()
                updated_data["daily_forecast"] = forecast_data.get("forecastDays", [])

            # Fetch hourly forecast if needed
            if endpoints_to_update.get(ENDPOINT_HOURLY):
                _LOGGER.debug("Fetching hourly forecast")
                hourly_params = {
                    **weather_params,
                    "hours": 240,  # Get 240 hours (10 days) of forecast
                }
                hourly_response = requests.get(
                    f"{API_BASE_URL}/forecast/hours:lookup",
                    params=hourly_params,
                    timeout=10,
                )
                hourly_response.raise_for_status()
                forecast_data = hourly_response.json()
                hourly_entries = forecast_data.get("forecastHours", [])
                updated_data["hourly_forecast"] = hourly_entries

                snow_total = _calculate_snow_forecast_next_24h(hourly_entries)
                if snow_total is not None:
                    updated_data["snow_forecast_24h"] = snow_total
                else:
                    updated_data["snow_forecast_24h"] = None

            # Fetch the minute forecast (nowcast) if needed
            if endpoints_to_update.get(ENDPOINT_MINUTE):
                _LOGGER.debug("Fetching minute forecast")
                try:
                    # Counted here rather than at scheduling time: this is the
                    # point past which a call is actually spent.
                    self._count_minute_call()
                    minute_response = requests.get(
                        f"{API_BASE_URL}/forecast/minutes:lookup",
                        params={
                            **weather_params,
                            # Never an exact count: the segment count is a
                            # product of window length and cadence, both
                            # undocumented and region-dependent.
                            "pageSize": MINUTE_PAGE_SIZE,
                        },
                        timeout=10,
                    )
                    minute_response.raise_for_status()
                    minute_data = minute_response.json()
                    if not isinstance(minute_data, dict):
                        minute_data = {}

                    if minute_data.get("nextPageToken"):
                        # A broken assumption to log. derive() measures coverage
                        # from the segments, so a short page slows polling rather
                        # than overpromising.
                        _LOGGER.warning(
                            "Minute forecast returned a page token at pageSize=%d; "
                            "the window is larger than one page and the forecast "
                            "is incomplete",
                            MINUTE_PAGE_SIZE,
                        )

                    updated_data["minute_segments"] = minute_data.get("segments") or []
                    updated_data["minute_forecast"] = nowcast.derive(
                        minute_data, dt_util.utcnow()
                    )
                except (requests.RequestException, ValueError) as err:
                    # Kept out of the shared error path so a pre-GA endpoint
                    # cannot take the rest of the integration down with it.
                    # ValueError covers a body that does not decode as JSON.
                    _LOGGER.warning("Minute forecast unavailable: %s", err)
                    updated_data["minute_forecast_error"] = str(err)

            # Fetch weather alerts if needed
            if endpoints_to_update.get(ENDPOINT_ALERTS):
                _LOGGER.debug("Fetching weather alerts")
                try:
                    alerts_response = requests.get(
                        f"{API_BASE_URL}/publicAlerts:lookup",
                        params=alerts_params,
                        timeout=10,
                    )
                    alerts_response.raise_for_status()
                    alerts_data = alerts_response.json()
                    updated_data["alerts"] = alerts_data.get("weatherAlerts", [])
                    # Mark alerts as supported for this location
                    if self.alerts_supported is None:
                        self.alerts_supported = True
                        _LOGGER.info("Weather alerts are supported for this location")
                except requests.HTTPError as err:
                    # Handle 404 errors gracefully - region doesn't support alerts
                    if err.response.status_code == 404:
                        # Mark alerts as not supported for this location
                        if self.alerts_supported is None:
                            self.alerts_supported = False
                            _LOGGER.info(
                                "Weather alerts not available for this location (HTTP 404). "
                                "This is normal for regions without alert coverage. "
                                "Warning sensors will not be created."
                            )
                        updated_data["alerts"] = []
                    else:
                        # Re-raise other HTTP errors
                        raise

            return updated_data

        except requests.HTTPError as err:
            _LOGGER.error("HTTP error fetching weather data: %s", err)
            if err.response.status_code in [401, 403]:
                raise UpdateFailed("Invalid API key or insufficient permissions") from err
            raise UpdateFailed(f"HTTP error: {err.response.status_code}") from err
        except requests.RequestException as err:
            _LOGGER.error("Request error fetching weather data: %s", err)
            raise UpdateFailed(f"Connection error: {err}") from err

    async def async_fetch_forecast_on_demand(self, endpoint: str) -> list[dict[str, Any]]:
        """Fetch a specific forecast endpoint on demand (for manual service calls)."""
        _LOGGER.debug("Fetching %s on demand", endpoint)
        try:
            # Fetch the specific endpoint. The minute call is counted where it
            # is made, so an on-demand fetch books itself.
            endpoints_to_update = {endpoint: True}

            updated_data = await self.hass.async_add_executor_job(
                self._fetch_weather_data,
                endpoints_to_update,
            )

            # Cache the data
            self.endpoint_data.update(updated_data)
            self.last_update[endpoint] = dt_util.now()

            # Return the appropriate forecast data
            if endpoint == ENDPOINT_DAILY:
                return updated_data.get("daily_forecast", [])
            elif endpoint == ENDPOINT_HOURLY:
                return updated_data.get("hourly_forecast", [])
            elif endpoint == ENDPOINT_MINUTE:
                # A real call, so it resets the schedule too.
                self._apply_minute_schedule(updated_data)
                return updated_data.get("minute_segments", [])
            else:
                return []

        except Exception as err:
            _LOGGER.error("Error fetching %s on demand: %s", endpoint, err)
            return []
