"""Weather condition tables for the Google Weather integration.

These tables live here rather than in weather.py because coordinator.py needs
the snow descriptors too. They were previously two hand-maintained lists in the
two modules, and adding a descriptor to one but not the other made the snow
sensor under-report while the weather entity looked correct.
"""
from __future__ import annotations

# Map Google Weather API condition types to Home Assistant condition types.
# Source enum: https://developers.google.com/maps/documentation/weather/reference/rest/v1/WeatherCondition
CONDITION_MAP = {
    "CLEAR": "sunny",
    "MOSTLY_CLEAR": "sunny",
    "PARTLY_CLOUDY": "partlycloudy",
    "MOSTLY_CLOUDY": "cloudy",
    "CLOUDY": "cloudy",
    "OVERCAST": "cloudy",
    "FOG": "fog",
    "WINDY": "windy",
    "WIND_AND_RAIN": "rainy",
    # Rain
    "LIGHT_RAIN": "rainy",
    "RAIN": "rainy",
    "HEAVY_RAIN": "pouring",
    "LIGHT_RAIN_SHOWERS": "rainy",
    "CHANCE_OF_SHOWERS": "rainy",
    "SCATTERED_SHOWERS": "rainy",
    "RAIN_SHOWERS": "rainy",
    "HEAVY_RAIN_SHOWERS": "pouring",
    "LIGHT_TO_MODERATE_RAIN": "rainy",
    "MODERATE_TO_HEAVY_RAIN": "pouring",
    "RAIN_PERIODICALLY_HEAVY": "pouring",
    "DRIZZLE": "rainy",
    # Snow
    "LIGHT_SNOW": "snowy",
    "SNOW": "snowy",
    "HEAVY_SNOW": "snowy",
    "LIGHT_SNOW_SHOWERS": "snowy",
    "CHANCE_OF_SNOW_SHOWERS": "snowy",
    "SCATTERED_SNOW_SHOWERS": "snowy",
    "SNOW_SHOWERS": "snowy",
    "HEAVY_SNOW_SHOWERS": "snowy",
    "LIGHT_TO_MODERATE_SNOW": "snowy",
    "MODERATE_TO_HEAVY_SNOW": "snowy",
    "SNOWSTORM": "snowy",
    "SNOW_PERIODICALLY_HEAVY": "snowy",
    "HEAVY_SNOW_STORM": "snowy",
    "BLOWING_SNOW": "snowy",
    "BLIZZARD": "snowy",
    # Mixed precipitation
    "RAIN_AND_SNOW": "snowy-rainy",
    "SLEET": "snowy-rainy",
    # Hail
    "HAIL": "hail",
    "HAIL_SHOWERS": "hail",
    # Thunderstorms
    "THUNDERSTORM": "lightning",
    "THUNDERSHOWER": "lightning-rainy",
    "LIGHT_THUNDERSTORM_RAIN": "lightning-rainy",
    "SCATTERED_THUNDERSTORMS": "lightning",
    "HEAVY_THUNDERSTORM": "lightning-rainy",
    "SEVERE_THUNDERSTORM": "lightning-rainy",
    # Severe. Home Assistant has no hurricane state, so these use the
    # "exceptional" catch-all rather than rendering as unknown.
    "TORNADO": "exceptional",
    "HURRICANE": "exceptional",
    "TROPICAL_STORM": "exceptional",
    "PARTLY_CLEAR": "partlycloudy",
}

# Conditions that count towards snow accumulation totals. Derived from
# CONDITION_MAP so a new snow descriptor only has to be added in one place.
# Note the coupling: remapping a descriptor away from "snowy" also drops it
# from snow accumulation. Mixed types (RAIN_AND_SNOW, SLEET) map to
# "snowy-rainy" and are excluded, which is deliberate — they report mixed
# precipitation rather than snow depth.
SNOW_CONDITION_TYPES = frozenset(
    condition for condition, state in CONDITION_MAP.items() if state == "snowy"
)
