"""Data coordinator for Google Weather integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    ENDPOINT_ALERTS,
    ENDPOINT_CURRENT,
    ENDPOINT_DAILY,
    ENDPOINT_HOURLY,
)

_LOGGER = logging.getLogger(__name__)


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
        self.unit_system = current_data.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)

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
        }

        # Cache data for each endpoint
        self.endpoint_data: dict[str, Any] = {}

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

        from datetime import time as dt_time

        start_time = dt_time(start_hour, start_min)
        end_time = dt_time(end_hour, end_min)

        # Handle cases where night period crosses midnight
        if start_time < end_time:
            return start_time <= now < end_time
        else:
            return now >= start_time or now < end_time

    def _should_update_endpoint(self, endpoint: str) -> bool:
        """Check if an endpoint should be updated based on configured intervals."""
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Google Weather API using smart polling."""
        try:
            # Check which endpoints need updating
            endpoints_to_update = {
                endpoint: self._should_update_endpoint(endpoint)
                for endpoint in [ENDPOINT_CURRENT, ENDPOINT_DAILY, ENDPOINT_HOURLY, ENDPOINT_ALERTS]
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
            # Prepare common parameters for weather endpoints (with units_system)
            weather_params = {
                "key": self.api_key,
                "location.latitude": self.latitude,
                "location.longitude": self.longitude,
                "units_system": self.unit_system,
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
                updated_data["hourly_forecast"] = forecast_data.get("forecastHours", [])

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
                except requests.HTTPError as err:
                    # Handle 404 errors gracefully - region doesn't support alerts
                    if err.response.status_code == 404:
                        _LOGGER.info(
                            "Weather alerts not available for this location (HTTP 404). "
                            "This is normal for regions without alert coverage."
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
