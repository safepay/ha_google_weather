# Forecast sensors

**Status:** Proposed · **Last reviewed:** 2026-09-15

> The daily forecast is already fetched, cached whole, and then mostly thrown
> away: the weather entity projects it into Home Assistant's fixed `Forecast`
> schema and discards the rest. Surfacing it as sensors costs no additional API
> calls, which makes this the only feature so far that can be added without
> spending from the 10,000-call budget. The work is therefore all in entity
> design, not in fetching.

## Objective

Give each forecast day first-class entities: a rollup whose state is that day's
high, plus discrete sensors for predicted rain, snow and rain chance. Put them
on their own device, behind an options-flow toggle, for a user-chosen number of
days.

## Why this costs nothing

The daily endpoint is fetched unconditionally. `include_daily_forecast` is
written as `True` in both config-flow paths and is never read to skip a fetch,
so the daily response is in the coordinator's cache on every install. The
weather entity's `async_forecast_daily` makes no request of its own — it is a
pure projection of that cache.

It is also a lossy projection. `Forecast` is a fixed Home Assistant schema, so
feels-like temperatures, sun and moon events, thunderstorm probability, maximum
heat index, ice thickness and the entire nighttime block are fetched, paid for,
and dropped on the floor. That discarded data is what makes these sensors worth
adding: they are not new information from Google, they are information already
bought and currently wasted.

This has a consequence for the config flow. Every existing toggle there costs
calls, and the flow tells users so — "Disable forecasts you don't need to save
API calls". Users have learned to read those switches as budget decisions. The
forecast-sensor toggle is the first that is free, so its description must say
so explicitly, or it will be left off by people protecting a budget it does not
touch.

## Why sensors rather than attributes on one entity

Only a sensor's *state* gets long-term statistics, a history graph and a direct
entity reference in an automation. An attribute needs `state_attr()` to reach,
is not recorded as its own series, and is rewritten in full on every state
change of its parent.

So the split is by use, not by tidiness. Quantities someone would chart or
trigger on — rain amount, rain chance, snow — get their own entities.
Descriptive fields read once at a glance — condition text, sunrise, sunset,
moon phase, wind direction, UV, humidity, cloud cover — stay as attributes on
that day's rollup.

The day's low is deliberately an attribute rather than a sixth entity. The
historical group has both a max and a min sensor, so this is an asymmetry, but
a second temperature entity per day multiplies by the day count and the low is
rarely charted on its own. If that proves wrong it can be promoted later;
promoting an attribute to an entity is additive, while removing an entity
orphans it.

## The `(24h)` names already mean something else

`Precipitation (24h)`, `Snow (24h)`, `Max Temperature (24h)`, `Min Temperature
(24h)` and `Temperature Change (24h)` all read `currentConditionsHistory` on
the current-conditions response. That block is the *previous* 24 hours —
rain that has already fallen, the highest temperature already observed. Only
`Snow Forecast (24h)` looks forward, and it is built separately by summing the
hourly cache over a rolling window.

New forecast sensors must not reuse the `(24h)` suffix. A day-0 total covers a
calendar day; a rolling window covers the next 24 hours from now; the two
numbers genuinely differ, and a shared suffix invites users to compare them as
though they were the same measurement taken twice. Name the new sensors for the
day they describe.

## Which entry is day 0

Not necessarily the first. The cached daily payload can be up to one polling
interval old, so shortly after midnight `forecastDays[0]` may still be
yesterday, and every sensor would silently report the wrong day for up to an
hour each night.

Select instead the first entry whose interval has not yet ended, and count day
*n* from there rather than from the head of the list. The interval timestamps
are absolute, which also keeps the choice correct when the location sits in a
different time zone to Home Assistant — a comparison against the local calendar
date would not.

## Naming and unique IDs

The keys are day-indexed:

- `forecast_day_<n>` — the rollup
- `precipitation_forecast_day_<n>`
- `snow_forecast_day_<n>`
- `precipitation_probability_day_<n>`

Three identifiers hang off those, deliberately decoupled:

- **Unique ID** stays `<location_slug>_<sensor_key>`, as everywhere else.
- **Entity ID** is set explicitly to `sensor.<location_slug>_<sensor_key>`, so
  it keeps the location prefix users write into dashboards and automations.
- **Friendly name** is the sensor's own name plus the day — *Precipitation
  Forecast Tomorrow* — with no location, which the `<Location> Forecast` device
  supplies instead. Day 0 reads *Today*, day 1 *Tomorrow*, and *Day &lt;n+1&gt;*
  beyond that.

Concretely, for location "home" and day 1:

```text
entity_id:     sensor.home_precipitation_forecast_day_1
unique_id:     home_precipitation_forecast_day_1
friendly name: Precipitation Forecast Tomorrow
device:        Home Forecast
```

The decoupling is forced rather than chosen. The key carries an index
(`day_1`) while the friendly name reads *Tomorrow*, so the entity ID cannot be
produced by slugifying the name, which is how the existing sensors derive
theirs.

Dropping the location from the friendly name is a deliberate divergence.
Everywhere else in this integration the name is prefixed with it — "Home
Temperature" — and the entity ID inherits the location only as a by-product of
that. Here the device carries the location and the name does not repeat it.
Worth noting that a friendly name can be changed later without orphaning
anything, unlike a unique ID, so if the inconsistency grates it is the cheap
half of the decision to revisit.

Keys of `forecast_today` and `forecast_tomorrow` were considered, to match the
friendly names exactly. Rejected: special-casing the first two entries
complicates every lookup for a cosmetic gain in the entity ID, and unique IDs
cannot be corrected later without orphaning entities that users have already
put on dashboards and in automations. The index is absolute and never shifts
meaning — day 0 is always today — so it is safe to fix now.

## Whole-day precipitation

Google reports precipitation per day part, not per day, so a day figure has to
be derived here. Two rules:

Accumulations add. `qpf` is expected accumulation over its part, so the daytime
and nighttime values sum to a day total.

Probabilities do not. Combining two parts as independent chances
(`1-(1-p₁)(1-p₂)`) assumes the halves are unrelated; they are driven by the
same system, so that formula overstates the risk. Take the higher of the two,
which is also what weather apps mean by "chance of rain today".

The parts also do not tile midnight to midnight — the daytime block starts near
dawn and the nighttime block runs into the following morning — so the rollup
publishes the window its totals actually cover. This follows the habit the
nowcast entities already set, where the segment width is published so a coarse
answer cannot read as a precise one.

## Config flow

Two new options:

- **Include forecast sensors** — default off. Turning it on creates up to forty
  entities; existing installs should not gain those silently on upgrade. The
  description states that it consumes no additional API calls.
- **Forecast days** — 1 to 10, default 1. The daily request already asks for ten
  days in a single call, so any value in that range is free. Going beyond ten
  means changing the request, which stays one call but is a different
  conversation about payload and budget, and is out of scope here.

## Pruning when the count falls

Turning the toggle off, or lowering the day count, must remove the now-unused
entities from the registry. The alert entities set this precedent already:
disabling alerts prunes them rather than leaving them behind.

Without it the failure is quiet and permanent. Entities for days that are no
longer produced stay in the registry as unavailable, keep working in existing
dashboards as broken references, and can only be cleared by hand. Lowering a
number in an options flow should not leave debris.

## Not in scope

- A rolling next-24-hours rain sensor — the hourly-cache analogue of `Snow
  Forecast (24h)`. Worth having, genuinely different from a calendar-day total,
  and dependent on hourly polling being enabled. Separate change.
- Renaming the existing `(24h)` historical sensors. Their README grouping
  already says "24-Hour Historical"; only the entity friendly names are
  ambiguous, and renaming them is a user-visible break for a cosmetic gain.
- Per-day-part entities. The daytime and nighttime blocks stay attributes;
  splitting each day into two more entities doubles the count for detail few
  automations need.
