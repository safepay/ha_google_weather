"""Parsing, derivation and polling arithmetic for the minute forecast.

The response shape does not match the rest of this API: the array is
``segments``, and ``type``, ``probability`` and ``intensity`` sit at the top
level of each segment rather than under a ``precipitation`` object. Captures in
``docs/plans/samples/minute-forecast/``, reasoning in
``docs/plans/minute-forecast.md``.

Free of Home Assistant imports, so it can be exercised without an instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from .const import (
    MINUTE_CAP_DORMANT,
    MINUTE_CAP_RELAXED,
    MINUTE_CAP_TIGHTENED,
    MINUTE_COVERAGE_FRACTION,
    MINUTE_DORMANT_LOOKAHEAD_HOURS,
    MINUTE_FLOOR_INTERVAL,
    MINUTE_GATE_HOURS,
    MINUTE_HORIZONS,
)

# What the already-fetched forecast says about the hours ahead.
OUTLOOK_WET = "wet"
OUTLOOK_DRY = "dry"
OUTLOOK_UNKNOWN = "unknown"

_LOGGER = logging.getLogger(__name__)

# Onset and cessation read WET_TYPES; accumulation reads RAIN_TYPES, so snow is
# never reported as rainfall.
WET_TYPES = frozenset({"RAIN", "SNOW", "HAIL"})
RAIN_TYPES = frozenset({"RAIN"})

# MID_ marks a step between the previous named level and this one, so MID_LIGHT
# is lighter than LIGHT. Display only: intensity labels a quantised qpf bucket
# and carries nothing qpf does not, so an unrecognised value costs nothing.
INTENSITY_LADDER = (
    "NO_INTENSITY",
    "MID_LIGHT",
    "LIGHT",
    "MID_MODERATE",
    "MODERATE",
    "MID_HEAVY",
    "HEAVY",
)

# Protobuf zero value: field never set. Not a rung, and not NO_INTENSITY, which
# is a real reading of no precipitation.
INTENSITY_UNSET = "PRECIPITATION_INTENSITY_UNSPECIFIED"

# Raw segments are never published: a two-minute region returns 180 per refresh
# and the recorder re-serialises attributes on every state change.
TIMELINE_BUCKET_MINUTES = 15


def _parse_time(value: Any) -> datetime | None:
    """Parse an RFC 3339 timestamp to an aware UTC datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    """Coerce a value to float, or None if it is missing or unusable."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quantity(block: Any) -> float | None:
    """Read the quantity out of a {unit, quantity} block."""
    if not isinstance(block, dict):
        return None
    return _number(block.get("quantity"))


@dataclass(frozen=True)
class Segment:
    """One segment of a minute forecast response."""

    start: datetime
    end: datetime
    precipitation_type: str
    probability: float | None
    qpf: float | None
    snowfall: float | None
    intensity: str | None

    @property
    def duration_minutes(self) -> float:
        """Width of this segment, and so the precision of any answer it gives."""
        return (self.end - self.start).total_seconds() / 60

    @property
    def is_wet(self) -> bool:
        """Read from type and qpf together, never from probability."""
        if self.precipitation_type not in WET_TYPES:
            return False
        return self.qpf is None or self.qpf > 0

    @property
    def is_rain(self) -> bool:
        """Whether this segment's precipitation is rain specifically."""
        return self.precipitation_type in RAIN_TYPES and self.is_wet


def parse_segments(payload: dict[str, Any]) -> list[Segment]:
    """Parse the segments out of a response, skipping anything unusable."""
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return []

    segments: list[Segment] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        frame = entry.get("timeFrame") or {}
        start = _parse_time(frame.get("startTime"))
        end = _parse_time(frame.get("endTime"))
        if start is None or end is None or end <= start:
            continue

        intensity = entry.get("intensity")
        if not isinstance(intensity, str) or intensity == INTENSITY_UNSET:
            intensity = None

        precipitation_type = entry.get("type")
        if not isinstance(precipitation_type, str):
            precipitation_type = "NONE"

        segments.append(
            Segment(
                start=start,
                end=end,
                precipitation_type=precipitation_type,
                probability=_number(entry.get("probability")),
                qpf=_quantity(entry.get("qpf")),
                snowfall=_quantity(entry.get("snowfallAmount")),
                intensity=intensity,
            )
        )

    segments.sort(key=lambda segment: segment.start)
    return segments


def _accumulate(segments: list[Segment], now: datetime, horizon_minutes: int | None) -> float:
    """Sum rain qpf over segments beginning within the horizon.

    Raw: weighting by probability understates the total roughly fourfold against
    the hourly forecast. A segment counts if it begins inside the horizon, so a
    horizon can overshoot by one segment; prorating would imply a resolution the
    quantised buckets do not have.
    """
    if horizon_minutes is None:
        cutoff = None
    else:
        cutoff = now + timedelta(minutes=horizon_minutes)

    total = 0.0
    for segment in segments:
        if cutoff is not None and segment.start >= cutoff:
            break
        if segment.is_rain and segment.qpf:
            total += segment.qpf
    return round(total, 3)


def _build_timeline(segments: list[Segment], now: datetime) -> list[dict[str, Any]]:
    """Downsample rain into fixed buckets for display."""
    if not segments:
        return []

    timeline: list[dict[str, Any]] = []
    bucket_start = now
    end = segments[-1].end

    while bucket_start < end:
        bucket_end = bucket_start + timedelta(minutes=TIMELINE_BUCKET_MINUTES)
        total = sum(
            segment.qpf
            for segment in segments
            if segment.is_rain
            and segment.qpf
            and bucket_start <= segment.start < bucket_end
        )
        timeline.append(
            {
                "start": bucket_start.isoformat().replace("+00:00", "Z"),
                "rain": round(total, 3),
            }
        )
        bucket_start = bucket_end

    return timeline


def derive(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Reduce a response to the scalars the entities publish.

    Reads whatever arrived rather than classifying the location: the same
    coordinates have returned different shapes hours apart, so there is nothing
    to latch. Precision travels with each segment.
    """
    segments = parse_segments(payload)

    # Segments do not tile overallPredictionTimeframe - captures overhang at the
    # start and fall short at the end - so clamp to now and measure coverage from
    # the segments, never from the declared window.
    upcoming = [segment for segment in segments if segment.end > now]

    derived: dict[str, Any] = {
        "available": bool(upcoming),
        "segment_count": len(upcoming),
        "page_truncated": bool(payload.get("nextPageToken")),
    }

    if not upcoming:
        _LOGGER.debug(
            "Minute forecast: no segments covering the present (parsed=%d)", len(segments)
        )
        return derived

    leading = upcoming[0]
    last = upcoming[-1]
    coverage_minutes = (last.end - now).total_seconds() / 60

    # The narrowest segment, not the leading one, for the same reason the
    # setup probe measures it that way: a response that leads with a
    # multi-hour block would otherwise report this location as hours wide,
    # and the options flow reads this to decide which intervals to offer.
    cadence_minutes = min(segment.duration_minutes for segment in upcoming)

    derived["coverage_minutes"] = round(coverage_minutes, 1)
    derived["cadence_minutes"] = round(cadence_minutes, 1)
    derived["window_end"] = last.end.isoformat().replace("+00:00", "Z")
    derived["precipitating_now"] = leading.is_wet
    derived["intensity"] = leading.intensity
    derived["probability"] = leading.probability

    # qpf is a per-segment total, not a rate: read as a rate the heaviest
    # observed segments come out as drizzle.
    if leading.qpf is not None and leading.duration_minutes > 0:
        derived["precipitation_rate"] = round(leading.qpf * 60 / leading.duration_minutes, 2)
    else:
        derived["precipitation_rate"] = None

    onset_index = next(
        (index for index, segment in enumerate(upcoming) if segment.is_wet), None
    )

    if onset_index is None:
        derived["starts_in"] = None
        derived["starts_at"] = None
        derived["onset_precision_minutes"] = None
        derived["onset_type"] = None
        derived["stops_in"] = None
        derived["truncated_by_window"] = False
    else:
        onset = upcoming[onset_index]
        derived["starts_in"] = (
            0 if onset_index == 0 else round((onset.start - now).total_seconds() / 60)
        )
        derived["starts_at"] = onset.start.isoformat().replace("+00:00", "Z")
        # The onset segment may be 2 minutes wide or several hours. Publishing
        # the width keeps a coarse answer from reading as a precise one.
        derived["onset_precision_minutes"] = round(onset.duration_minutes, 1)
        derived["onset_type"] = onset.precipitation_type

        dry_index = next(
            (
                index
                for index in range(onset_index + 1, len(upcoming))
                if not upcoming[index].is_wet
            ),
            None,
        )
        if dry_index is None:
            # Runs to the window edge: the forecast says nothing about when it
            # stops, and the edge would claim it ends when the data runs out.
            derived["stops_in"] = None
            derived["truncated_by_window"] = True
        else:
            derived["stops_in"] = round(
                (upcoming[dry_index].start - now).total_seconds() / 60
            )
            derived["truncated_by_window"] = False

    for horizon in MINUTE_HORIZONS:
        derived[f"rain_{horizon}min"] = _accumulate(upcoming, now, horizon)

    # A lower bound when precipitation runs to the window edge.
    derived["rain_rest_of_window"] = _accumulate(upcoming, now, None)
    derived["timeline"] = _build_timeline(upcoming, now)

    return derived


def forecast_outlook(
    *,
    current: dict[str, Any] | None,
    hourly: list[dict[str, Any]] | None,
    daily: list[dict[str, Any]] | None,
    now: datetime,
    is_night: bool,
    threshold: int,
) -> str:
    """What the already-fetched forecast says: wet, dry, or unknown.

    This is what starts and stops nowcast polling. One predicate, two sources:
    hourly where enabled, daily otherwise. Both are already fetched, so the gate
    is free - and since turning hourly off is what frees the headroom this
    feature needs, an hourly-only gate would be unavailable to its own audience.

    "dry" requires forecast data actually saying so; absent data is "unknown",
    which polls normally rather than going quiet on no evidence. Never reads the
    nowcast's own probability.
    """
    if _currently_precipitating(current):
        return OUTLOOK_WET

    if hourly:
        if _hourly_gate(hourly, now, threshold, MINUTE_GATE_HOURS):
            return OUTLOOK_WET
        # Dormancy spans longer than the tighten window, so it has to be clear
        # across the whole of it, and only counts if the hours are really there.
        covered, wet = _hourly_span(hourly, now, MINUTE_DORMANT_LOOKAHEAD_HOURS, threshold)
        if covered and not wet:
            return OUTLOOK_DRY
        return OUTLOOK_UNKNOWN

    block = _daily_block(daily, is_night)
    if block is None:
        return OUTLOOK_UNKNOWN
    return OUTLOOK_WET if _block_exceeds(block, threshold) else OUTLOOK_DRY


def _currently_precipitating(current: dict[str, Any] | None) -> bool:
    """Whether current conditions already report precipitation falling."""
    if not isinstance(current, dict):
        return False
    precipitation = current.get("precipitation") or {}
    if _quantity(precipitation.get("qpf")):
        return True
    probability = precipitation.get("probability") or {}
    return probability.get("type") in WET_TYPES and bool(
        _number(probability.get("percent"))
    )


def _block_exceeds(block: Any, threshold: int) -> bool:
    """Whether a forecast block's precipitation or thunderstorm odds clear the gate."""
    if not isinstance(block, dict):
        return False

    probability = ((block.get("precipitation") or {}).get("probability") or {})
    percent = _number(probability.get("percent"))
    if percent is not None and percent >= threshold:
        return True

    # Convection is what forecasts miss and radar nowcasting catches.
    thunderstorm = _number(block.get("thunderstormProbability"))
    return thunderstorm is not None and thunderstorm > 0


def _hourly_gate(
    hourly: list[dict[str, Any]], now: datetime, threshold: int, hours: int
) -> bool:
    """Whether any hour in the next `hours` clears the gate."""
    return _hourly_span(hourly, now, hours, threshold)[1]


def _hourly_span(
    hourly: list[dict[str, Any]], now: datetime, hours: int, threshold: int
) -> tuple[bool, bool]:
    """Return (the span is actually covered, any hour in it clears the gate)."""
    cutoff = now + timedelta(hours=hours)
    latest: datetime | None = None
    wet = False

    for hour in hourly:
        start = _parse_time((hour.get("interval") or {}).get("startTime"))
        if start is None or start >= cutoff or start + timedelta(hours=1) <= now:
            continue
        if latest is None or start > latest:
            latest = start
        if _block_exceeds(hour, threshold):
            wet = True

    # One hour short of the cutoff still counts: the last entry covers the hour
    # that follows it.
    covered = latest is not None and latest + timedelta(hours=1) >= cutoff
    return covered, wet


def _daily_block(daily: list[dict[str, Any]] | None, is_night: bool) -> dict[str, Any] | None:
    """Today's day or night block, when hourly forecasts are unavailable.

    Coarser by construction: 40% across a sixteen-hour block keeps the nowcast
    awake all day for evening rain. Degrading is the point.
    """
    if not daily:
        return None
    today = daily[0]
    if not isinstance(today, dict):
        return None
    block = today.get("nighttimeForecast" if is_night else "daytimeForecast")
    return block if isinstance(block, dict) else None


def next_poll_minutes(
    derived: dict[str, Any],
    *,
    outlook: str = OUTLOOK_UNKNOWN,
    floor: int = MINUTE_FLOOR_INTERVAL,
) -> int:
    """Minutes to wait before the next nowcast call.

        sleep = clamp(minutes_until_first_wet_segment / 2, floor, cap)

    A dry response guarantees no rain for the span it covers, so it is a licence
    not to poll. Rain already falling gives an onset of zero and pins the
    interval to the floor. See MINUTE_MIN_INTERVAL_OPTIONS in const.py.

    `outlook` comes from the daily or hourly forecast and decides whether the
    nowcast polls at all: "dry" stops it until its window expires.
    """
    floor = max(1, floor)
    coverage = derived.get("coverage_minutes")

    # Dormant: the forecast says no rain and the nowcast agrees, so stop polling
    # until the window it guaranteed runs out. The nowcast's own data wins - an
    # onset it can see keeps polling regardless of what the forecast said.
    if (
        outlook == OUTLOOK_DRY
        and derived.get("starts_in") is None
        and not derived.get("precipitating_now")
    ):
        return int(min(MINUTE_CAP_DORMANT, coverage) if coverage else MINUTE_CAP_DORMANT)

    cap = MINUTE_CAP_TIGHTENED if outlook == OUTLOOK_WET else MINUTE_CAP_RELAXED

    # Never promise longer than the last response covered. At a full window this
    # changes nothing; on a short page it tightens rather than overpromising.
    if coverage:
        cap = min(cap, max(floor, coverage * MINUTE_COVERAGE_FRACTION))

    starts_in = derived.get("starts_in")
    candidate = cap if starts_in is None else starts_in / 2

    return int(max(floor, min(cap, candidate)))
