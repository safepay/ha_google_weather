"""Data coordinator for Google Weather integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    CONF_UNIT_SYSTEM,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UNIT_SYSTEM,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GoogleWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage Google Weather API calls."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: OAuth2Session,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.session = session
        self.entry = entry
        self.latitude = entry.options.get(CONF_LATITUDE) or entry.data.get(CONF_LATITUDE)
        self.longitude = entry.options.get(CONF_LONGITUDE) or entry.data.get(CONF_LONGITUDE)
        self.unit_system = entry.options.get(CONF_UNIT_SYSTEM) or entry.data.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Google Weather API."""
        try:
            # Refresh token if needed
            await self.session.async_ensure_token_valid()

            # Get credentials
            token = self.session.token
            credentials = Credentials(
                token=token["access_token"],
                refresh_token=token.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.session.implementation.client_id,
                client_secret=self.session.implementation.client_secret,
            )

            # Call Google Weather API
            weather_data = await self.hass.async_add_executor_job(
                self._fetch_weather_data, credentials
            )

            return weather_data

        except Exception as err:
            _LOGGER.error("Error fetching weather data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def _fetch_weather_data(self, credentials: Credentials) -> dict[str, Any]:
        """Fetch weather data from Google Weather API (runs in executor)."""
        try:
            # Refresh credentials if needed
            if credentials.expired:
                credentials.refresh(Request())

            # Prepare common parameters
            params = {
                "location.latitude": self.latitude,
                "location.longitude": self.longitude,
                "unitsSystem": self.unit_system,
            }

            headers = {
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            }

            # Fetch current conditions
            current_response = requests.get(
                f"{API_BASE_URL}/currentConditions:lookup",
                params=params,
                headers=headers,
                timeout=30,
            )
            current_response.raise_for_status()
            current_data = current_response.json()

            # Fetch daily forecast (10 days)
            daily_params = {**params, "days": 10}
            daily_response = requests.get(
                f"{API_BASE_URL}/forecast/days:lookup",
                params=daily_params,
                headers=headers,
                timeout=30,
            )
            daily_response.raise_for_status()
            daily_data = daily_response.json()

            # Fetch hourly forecast (240 hours / 10 days)
            hourly_params = {**params, "hours": 240}
            hourly_response = requests.get(
                f"{API_BASE_URL}/forecast/hours:lookup",
                params=hourly_params,
                headers=headers,
                timeout=30,
            )
            hourly_response.raise_for_status()
            hourly_data = hourly_response.json()

            # Fetch weather alerts
            alerts_response = requests.get(
                f"{API_BASE_URL}/publicAlerts:lookup",
                params=params,
                headers=headers,
                timeout=30,
            )
            alerts_response.raise_for_status()
            alerts_data = alerts_response.json()

            # Combine all data into a single structure
            return {
                "current": current_data,
                "daily_forecast": daily_data.get("forecastDays", []),
                "hourly_forecast": hourly_data.get("forecastHours", []),
                "alerts": alerts_data.get("weatherAlerts", []),
                "timezone": daily_data.get("timeZone", {}),
            }

        except requests.exceptions.RequestException as err:
            _LOGGER.error("Failed to fetch weather data: %s", err)
            raise UpdateFailed(f"API request failed: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error fetching weather data: %s", err)
            raise
