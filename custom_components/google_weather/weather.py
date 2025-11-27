"""Weather platform for Google Weather integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfLength,
    UnitOfPrecipitationDepth,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INCLUDE_DAILY_FORECAST,
    CONF_INCLUDE_HOURLY_FORECAST,
    CONF_LOCATION,
    CONF_UNIT_SYSTEM,
    DEFAULT_INCLUDE_DAILY_FORECAST,
    DEFAULT_INCLUDE_HOURLY_FORECAST,
    DOMAIN,
    UNIT_SYSTEM_IMPERIAL,
)
from .coordinator import GoogleWeatherCoordinator

_LOGGER = logging.getLogger(__name__)

# Map Google Weather API condition types to Home Assistant condition types
CONDITION_MAP = {
    "CLEAR": "sunny",
    "MOSTLY_CLEAR": "sunny",
    "PARTLY_CLOUDY": "partlycloudy",
    "MOSTLY_CLOUDY": "cloudy",
    "CLOUDY": "cloudy",
    "OVERCAST": "cloudy",
    "FOG": "fog",
    "LIGHT_RAIN": "rainy",
    "RAIN": "rainy",
    "HEAVY_RAIN": "pouring",
    "RAIN_SHOWERS": "rainy",
    "SCATTERED_SHOWERS": "rainy",
    "DRIZZLE": "rainy",
    "LIGHT_SNOW": "snowy",
    "SNOW": "snowy",
    "HEAVY_SNOW": "snowy",
    "SNOW_SHOWERS": "snowy",
    "BLIZZARD": "snowy",
    "SLEET": "snowy-rainy",
    "HAIL": "hail",
    "THUNDERSTORM": "lightning",
    "SEVERE_THUNDERSTORM": "lightning-rainy",
    "TORNADO": "exceptional",
    "HURRICANE": "hurricane",
    "TROPICAL_STORM": "hurricane",
    "WINDY": "windy",
    "PARTLY_CLEAR": "partlycloudy",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather entity."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]

    location = entry.data.get(CONF_LOCATION, "home")

    async_add_entities([GoogleWeatherEntity(coordinator, entry, location)])


class GoogleWeatherEntity(CoordinatorEntity[GoogleWeatherCoordinator], WeatherEntity):
    """Representation of a Google Weather entity."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        location: str,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)

        # Set supported features based on configuration
        current_data = {**entry.data, **entry.options}
        supported_features = 0
        if current_data.get(CONF_INCLUDE_DAILY_FORECAST, DEFAULT_INCLUDE_DAILY_FORECAST):
            supported_features |= WeatherEntityFeature.FORECAST_DAILY
        if current_data.get(CONF_INCLUDE_HOURLY_FORECAST, DEFAULT_INCLUDE_HOURLY_FORECAST):
            supported_features |= WeatherEntityFeature.FORECAST_HOURLY
        self._attr_supported_features = supported_features

        # Use location directly for entity ID (slugified)
        location_slug = location.lower().replace(" ", "_")

        # Create friendly name from location (title case)
        location_name = location.replace("_", " ").title()

        # Set unique_id, explicit friendly name, and device info (has_entity_name = False)
        self._attr_unique_id = f"{location_slug}_weather"
        self._attr_name = location_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{location_name} Weather",
            "manufacturer": "Google",
            "model": "Weather API",
            "sw_version": "v1",
        }

        # Set units based on unit system - API returns values in the requested unit system
        unit_system = entry.options.get(CONF_UNIT_SYSTEM) or entry.data.get(CONF_UNIT_SYSTEM, "METRIC")
        if unit_system == UNIT_SYSTEM_IMPERIAL:
            self._attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
            self._attr_native_pressure_unit = UnitOfPressure.MBAR  # API does not convert pressure
            self._attr_native_wind_speed_unit = UnitOfSpeed.MILES_PER_HOUR
            self._attr_native_precipitation_unit = UnitOfPrecipitationDepth.INCHES
            self._attr_native_visibility_unit = UnitOfLength.MILES
        else:
            self._attr_native_temperature_unit = UnitOfTemperature.CELSIUS
            self._attr_native_pressure_unit = UnitOfPressure.MBAR
            self._attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
            self._attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
            self._attr_native_visibility_unit = UnitOfLength.KILOMETERS

    def _get_current_data(self) -> dict[str, Any] | None:
        """Get current weather data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current")

    def _map_condition(self, condition_type: str | None) -> str | None:
        """Map Google Weather condition type to Home Assistant condition."""
        if not condition_type:
            return None
        return CONDITION_MAP.get(condition_type, condition_type.lower())

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        current = self._get_current_data()
        if not current:
            return None

        weather_condition = current.get("weatherCondition", {})
        condition_type = weather_condition.get("type")
        return self._map_condition(condition_type)

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        current = self._get_current_data()
        if not current:
            return None

        temp_data = current.get("temperature", {})
        return temp_data.get("degrees")

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the apparent (feels like) temperature."""
        current = self._get_current_data()
        if not current:
            return None

        feels_like = current.get("feelsLikeTemperature", {})
        return feels_like.get("degrees")

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        current = self._get_current_data()
        if not current:
            return None
        return current.get("relativeHumidity")

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        current = self._get_current_data()
        if not current:
            return None

        pressure = current.get("airPressure", {})
        return pressure.get("meanSeaLevelMillibars")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        current = self._get_current_data()
        if not current:
            return None

        wind = current.get("wind", {})
        speed = wind.get("speed", {})
        return speed.get("value")

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        current = self._get_current_data()
        if not current:
            return None

        wind = current.get("wind", {})
        direction = wind.get("direction", {})
        return direction.get("degrees")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the wind gust speed."""
        current = self._get_current_data()
        if not current:
            return None

        wind = current.get("wind", {})
        gust = wind.get("gust", {})
        return gust.get("value")

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility."""
        current = self._get_current_data()
        if not current:
            return None

        visibility = current.get("visibility", {})
        return visibility.get("distance")

    @property
    def cloud_coverage(self) -> float | None:
        """Return the cloud coverage."""
        current = self._get_current_data()
        if not current:
            return None
        return current.get("cloudCover")

    @property
    def uv_index(self) -> float | None:
        """Return the UV index."""
        current = self._get_current_data()
        if not current:
            return None
        return current.get("uvIndex")

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point."""
        current = self._get_current_data()
        if not current:
            return None

        dew_point = current.get("dewPoint", {})
        return dew_point.get("degrees")

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        # Return empty list if daily forecasts are disabled
        if not (self._attr_supported_features & WeatherEntityFeature.FORECAST_DAILY):
            return []

        try:
            if not self.coordinator.data:
                _LOGGER.debug("No coordinator data available for daily forecast")
                return None

            daily_forecast = self.coordinator.data.get("daily_forecast", [])
            _LOGGER.debug("Daily forecast data: %d days available", len(daily_forecast))

            if not daily_forecast:
                _LOGGER.warning("Daily forecast data is empty")
                return None

            forecasts: list[Forecast] = []

            for day in daily_forecast:
                display_date = day.get("displayDate", {})
                datetime_str = f"{display_date.get('year')}-{display_date.get('month'):02d}-{display_date.get('day'):02d}"

                daytime = day.get("daytimeForecast", {})
                weather_condition = daytime.get("weatherCondition", {})

                forecast = Forecast(
                    datetime=datetime_str,
                    condition=self._map_condition(weather_condition.get("type")),
                    native_temperature=day.get("maxTemperature", {}).get("degrees"),
                    native_templow=day.get("minTemperature", {}).get("degrees"),
                    native_precipitation=daytime.get("precipitation", {}).get("qpf", {}).get("quantity"),
                    precipitation_probability=daytime.get("precipitation", {}).get("probability", {}).get("percent"),
                    native_wind_speed=daytime.get("wind", {}).get("speed", {}).get("value"),
                    wind_bearing=daytime.get("wind", {}).get("direction", {}).get("degrees"),
                    humidity=daytime.get("relativeHumidity"),
                    uv_index=daytime.get("uvIndex"),
                    cloud_coverage=daytime.get("cloudCover"),
                )
                forecasts.append(forecast)

            _LOGGER.debug("Successfully created %d daily forecasts", len(forecasts))
            return forecasts
        except Exception as err:
            _LOGGER.error("Error creating daily forecast: %s", err, exc_info=True)
            return None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        # Return empty list if hourly forecasts are disabled
        if not (self._attr_supported_features & WeatherEntityFeature.FORECAST_HOURLY):
            return []

        try:
            if not self.coordinator.data:
                _LOGGER.debug("No coordinator data available for hourly forecast")
                return None

            hourly_forecast = self.coordinator.data.get("hourly_forecast", [])
            _LOGGER.debug("Hourly forecast data: %d hours available", len(hourly_forecast))

            if not hourly_forecast:
                _LOGGER.warning("Hourly forecast data is empty")
                return None

            forecasts: list[Forecast] = []

            for hour in hourly_forecast:
                interval = hour.get("interval", {})
                start_time = interval.get("startTime")

                if not start_time:
                    continue

                # Parse ISO 8601 datetime
                dt = dt_util.parse_datetime(start_time)
                if not dt:
                    continue

                weather_condition = hour.get("weatherCondition", {})

                forecast = Forecast(
                    datetime=dt.isoformat(),
                    condition=self._map_condition(weather_condition.get("type")),
                    native_temperature=hour.get("temperature", {}).get("degrees"),
                    native_apparent_temperature=hour.get("feelsLikeTemperature", {}).get("degrees"),
                    native_precipitation=hour.get("precipitation", {}).get("qpf", {}).get("quantity"),
                    precipitation_probability=hour.get("precipitation", {}).get("probability", {}).get("percent"),
                    native_wind_speed=hour.get("wind", {}).get("speed", {}).get("value"),
                    wind_bearing=hour.get("wind", {}).get("direction", {}).get("degrees"),
                    native_wind_gust_speed=hour.get("wind", {}).get("gust", {}).get("value"),
                    humidity=hour.get("relativeHumidity"),
                    native_pressure=hour.get("airPressure", {}).get("meanSeaLevelMillibars"),
                    uv_index=hour.get("uvIndex"),
                    cloud_coverage=hour.get("cloudCover"),
                )
                forecasts.append(forecast)

            _LOGGER.debug("Successfully created %d hourly forecasts", len(forecasts))
            return forecasts
        except Exception as err:
            _LOGGER.error("Error creating hourly forecast: %s", err, exc_info=True)
            return None
