"""Day-level values derived from the Google daily forecast response.

Deliberately free of Home Assistant imports: everything here is a function of
the decoded JSON, so it can be exercised without a running instance. Keep it
that way — the date arithmetic and the day-part rollups are the parts of this
integration most worth testing directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .const import CARDINAL_DIRECTION_MAP

# Metric keys. A sensor key is one of these with the day offset appended.
KEY_HIGH = "forecast_high"
KEY_LOW = "forecast_low"
KEY_PRECIPITATION = "forecast_precipitation"
KEY_SNOW = "forecast_snow"
KEY_PRECIPITATION_PROBABILITY = "forecast_precipitation_probability"

FORECAST_METRIC_KEYS: tuple[str, ...] = (
    KEY_HIGH,
    KEY_LOW,
    KEY_PRECIPITATION,
    KEY_SNOW,
    KEY_PRECIPITATION_PROBABILITY,
)

# Carried under both "day_" and "night_", never unprefixed: each has a
# whole-day sensor of its own, and an unprefixed copy of the daytime half
# would report a different number under the same name.
SPLIT_ATTRIBUTES = (
    "precipitation",
    "snow",
    "precipitation_probability",
    "precipitation_type",
)

# Descriptive values worth having for the night as well. The daytime copy of
# these stays unprefixed, since that is the figure a forecast normally means.
NIGHT_ATTRIBUTES = (
    "condition",
    "condition_type",
    "cloud_cover",
    "wind_speed",
)


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an RFC 3339 timestamp, tolerating a trailing Z."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A timestamp without an offset would raise on comparison; assume UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def drop_expired_days(
    days: list[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    """Trim leading forecast days whose interval has already ended.

    The cached daily response is up to a polling interval old, so shortly after
    local midnight its first entry can still be yesterday. Trimming once, where
    the data is stored, keeps index 0 meaning today for every consumer rather
    than making each of them re-derive it.
    """
    moment = now or datetime.now(timezone.utc)
    for index, day in enumerate(days):
        end = _parse_timestamp((day.get("interval") or {}).get("endTime"))
        # An unreadable interval stops the scan rather than discarding the day.
        if end is None or end > moment:
            return days[index:] if index else days
    # Every day has expired, which means the response is long stale. Serving it
    # matches what the sensors did before the trim existed.
    return days


def get_forecast_day(days: list[dict[str, Any]], offset: int) -> dict[str, Any]:
    """Return one day of the forecast, counting today as 0."""
    return days[offset] if 0 <= offset < len(days) else {}


def _degrees(day: dict[str, Any], key: str) -> float | None:
    """Read one of the day's temperature fields."""
    return (day.get(key) or {}).get("degrees")


def _precipitation(block: dict[str, Any], key: str) -> float | None:
    """Read an accumulation out of a day part's precipitation."""
    return ((block.get("precipitation") or {}).get(key) or {}).get("quantity")


def _probability(block: dict[str, Any]) -> int | None:
    """Read a day part's chance of precipitation."""
    return ((block.get("precipitation") or {}).get("probability") or {}).get("percent")


def _day_part_attributes(block: dict[str, Any]) -> dict[str, Any]:
    """Flatten one daytimeForecast or nighttimeForecast block."""
    condition = block.get("weatherCondition") or {}
    wind = block.get("wind") or {}
    direction = wind.get("direction") or {}
    return {
        "condition": (condition.get("description") or {}).get("text"),
        "condition_type": condition.get("type"),
        "humidity": block.get("relativeHumidity"),
        "uv_index": block.get("uvIndex"),
        "cloud_cover": block.get("cloudCover"),
        "precipitation_probability": _probability(block),
        "precipitation_type": (
            (block.get("precipitation") or {}).get("probability") or {}
        ).get("type"),
        "precipitation": _precipitation(block, "qpf"),
        "snow": _precipitation(block, "snowQpf"),
        "thunderstorm_probability": block.get("thunderstormProbability"),
        "wind_speed": (wind.get("speed") or {}).get("value"),
        "wind_gust": (wind.get("gust") or {}).get("value"),
        "wind_bearing": direction.get("degrees"),
        "wind_direction": CARDINAL_DIRECTION_MAP.get(direction.get("cardinal")),
    }


def get_forecast_high(days: list[dict[str, Any]], offset: int) -> float | None:
    """Return the day's forecast high, the state of the rollup sensor."""
    return _degrees(get_forecast_day(days, offset), "maxTemperature")


def get_forecast_low(days: list[dict[str, Any]], offset: int) -> float | None:
    """Return the day's forecast low."""
    return _degrees(get_forecast_day(days, offset), "minTemperature")


def _accumulation(days: list[dict[str, Any]], offset: int, key: str) -> float | None:
    """Total one accumulation across the day's two parts, which do not overlap."""
    day = get_forecast_day(days, offset)
    amounts = [
        _precipitation(day.get(part) or {}, key)
        for part in ("daytimeForecast", "nighttimeForecast")
    ]
    present = [amount for amount in amounts if amount is not None]
    # Rounded: summing floats out of JSON leaves 0.30000000000000004.
    return round(sum(present), 3) if present else None


def get_forecast_precipitation(days: list[dict[str, Any]], offset: int) -> float | None:
    """Return the day's total expected rain."""
    return _accumulation(days, offset, "qpf")


def get_forecast_snow(days: list[dict[str, Any]], offset: int) -> float | None:
    """Return the day's total expected snow."""
    return _accumulation(days, offset, "snowQpf")


def get_forecast_probability(days: list[dict[str, Any]], offset: int) -> int | None:
    """Return the day's chance of precipitation, as the higher of its parts.

    Not combined as independent chances: both halves are driven by the same
    system, so that would overstate the risk.
    """
    day = get_forecast_day(days, offset)
    chances = [
        _probability(day.get(part) or {})
        for part in ("daytimeForecast", "nighttimeForecast")
    ]
    present = [chance for chance in chances if chance is not None]
    return max(present) if present else None


def get_forecast_attributes(days: list[dict[str, Any]], offset: int) -> dict[str, Any]:
    """Expose the rest of the day, which the weather entity's schema drops."""
    day = get_forecast_day(days, offset)
    if not day:
        return {}

    daytime = _day_part_attributes(day.get("daytimeForecast") or {})
    nighttime = _day_part_attributes(day.get("nighttimeForecast") or {})
    sun = day.get("sunEvents") or {}
    moon = day.get("moonEvents") or {}

    # High and low are omitted: each has its own entity.
    attributes: dict[str, Any] = {
        "feels_like_high": _degrees(day, "feelsLikeMaxTemperature"),
        "feels_like_low": _degrees(day, "feelsLikeMinTemperature"),
        "max_heat_index": _degrees(day, "maxHeatIndex"),
        "sunrise": sun.get("sunriseTime"),
        "sunset": sun.get("sunsetTime"),
        "moon_phase": moon.get("moonPhase"),
        # The parts do not tile midnight to midnight, so publish the real window.
        "forecast_window_start": (
            (day.get("daytimeForecast") or {}).get("interval") or {}
        ).get("startTime"),
        "forecast_window_end": (
            (day.get("nighttimeForecast") or {}).get("interval") or {}
        ).get("endTime"),
    }

    attributes.update(
        {key: value for key, value in daytime.items() if key not in SPLIT_ATTRIBUTES}
    )
    attributes.update({f"day_{key}": daytime[key] for key in SPLIT_ATTRIBUTES})
    attributes.update(
        {
            f"night_{key}": nighttime[key]
            for key in (*NIGHT_ATTRIBUTES, *SPLIT_ATTRIBUTES)
        }
    )

    return attributes


def forecast_sensor_keys(days: int) -> list[str]:
    """Every forecast sensor key up to a day count, for registry cleanup."""
    return [
        f"{metric}_{offset}"
        for offset in range(days)
        for metric in FORECAST_METRIC_KEYS
    ]
