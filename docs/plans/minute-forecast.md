# Minute forecast (nowcast) support

**Status:** Proposed · **Last reviewed:** 2026-09-08

## Objective

Answer two questions the current entities cannot: *when will rain start* and
*how much will fall*. Google's experimental minute forecast endpoint returns a
six-hour precipitation nowcast in roughly two-minute segments, which is the
right resolution for both.

## The endpoint

`GET /v1/forecast/minutes:lookup`, on the same host and with the same
`location.latitude` / `location.longitude` / `unitsSystem` parameters the
coordinator already builds for the other weather endpoints, so it needs no new
auth or request plumbing.

Each segment carries a time frame, a precipitation `type` (`NONE`, `RAIN`,
`SNOW`, `HAIL`), a `probability`, a `qpf` quantity, a `snowfallAmount` and an
`intensity` (`NO_INTENSITY`, `LIGHT`, `MODERATE`, `HEAVY`). Onset is the first
non-`NONE` segment; accumulation is the sum of `qpf` over a window.

The endpoint is **Experimental (pre-GA)**. It is absent from the versioned REST
reference, and the API FAQ still claims nowcasting is not offered at all — only
the guide page documents it. Treat the response shape as unstable and guard
every read, more strictly than for the GA endpoints.

## Why sensors, not the weather entity

Home Assistant's `WeatherEntity` supports daily, hourly and twice-daily
forecasts only. There is no minutely forecast type, so none of this can be
attached to the weather entity. It surfaces as sensors, and `weather.py` is
untouched by this work.

## The constraint: a single call budget

Google bills the whole Weather API under one "Weather Usage" SKU, so nowcast
calls come out of the same 10,000-per-month free tier as everything else. The
documented defaults already spend about 8,640, leaving roughly 1,360 calls of
headroom.

Flat polling does not fit in that. The endpoint costs `43200 / interval` calls
per month, so even a 30-minute interval spends 1,440 — over budget before the
nowcast is useful at all, and a genuinely useful 5-minute interval would cost
8,640 on its own.

## Design: let the forecast schedule itself

The decisive property is that a response is a **six-hour lookahead, not a
snapshot**. A response showing `NONE` across every segment is a guarantee that
rain cannot begin for six hours — so it is also a licence not to poll. Polling
frequency should therefore be derived from the data already in hand:

```text
sleep = clamp(minutes_until_first_wet_segment / 2, floor, cap)
```

with a floor of about 3 minutes and a cap that depends on whether rain is
expected at all (below). Precipitation already falling pins it to the floor.

This was chosen over a fixed day/night interval pair, as used by the other
endpoints, for two reasons. The day/night split suits data whose *value* varies
by time of day, which does not describe rain onset — arguably it matters more
overnight. And a fixed interval spends calls uniformly, whereas the whole cost
problem is that calls are only worth making as rain approaches.

An intermediate "armed" tier polling every 20 minutes was considered and
rejected. Because a dry response already guarantees six dry hours, that tier
buys almost no onset precision while costing several hundred calls a month.

## Why the gate reads the daily forecast, not the hourly one

The cap is set from precipitation probability in a forecast the coordinator has
already fetched and paid for — no extra calls.

That gate reads the **daily** forecast, not the hourly one. Hourly forecasts are
user-optional and many users disable them to save calls, so a gate depending on
hourly silently loses its signal for exactly the people most concerned about
budget. Daily forecasts are hard-coded on in both the config and options flows,
so `daytimeForecast` / `nighttimeForecast` precipitation probability is always
available.

Daily is coarser — a probability across a sixteen-hour block says nothing about
which hours — but that barely matters here, because the gate only sets the cap
on how long a *dry* response is trusted. The expensive part, polling every few
minutes while rain is inbound, is driven by the nowcast's own segments. Where
hourly forecasts are enabled they can sharpen the cap, since their six-hour
lookahead matches the nowcast window exactly; this is a refinement, never a
dependency.

Two further signals are free and should feed the same predicate: current
conditions already reporting rain should go straight to the floor, and daily
`thunderstormProbability` should tighten the cap even when rain probability is
low, since convective showers are the case hourly and daily guidance most often
misses and radar nowcasting handles best.

## Estimated cost

Roughly 1,260 calls per month for a temperate climate — about twenty dry days
at a two-hour cap, plus ten days carrying a few hours of rain each. That fits
the existing headroom without reducing any other endpoint's interval.

The figure is weather-dependent, which changes what the config flow's
confirmation screen can promise: today it does exact arithmetic, and for this
endpoint it can only offer a range. That argues for tracking calls actually made
and exposing the running total as a diagnostic sensor, with the nowcast falling
back to its cap when a ceiling is reached. Worth doing for the other endpoints
too.

## Entities

Gated on a new opt-in, defaulting to off because the endpoint is pre-GA:

- minutes until precipitation starts (duration)
- expected precipitation over the next 60 minutes (precipitation depth)
- minutes until precipitation stops (duration)
- a binary sensor for precipitation expected within the next hour

Derived values should be computed at fetch time in the coordinator and cached,
following the existing 24-hour snow total, so the sensors stay simple lookups.

Do not put all ~180 raw segments in a state attribute. The recorder
re-serialises attributes on every state change, and a payload that size is
enough to notice. Downsample to ten-minute buckets for the attribute, or keep it
out of the recorder.

## Config flow

An include checkbox in the forecast step of both the config and options flows,
plus a single threshold field — the rain probability at which the cap tightens.
Tiered polling means no day/night interval fields are needed for this endpoint,
so the added configuration surface is one checkbox and one number.

The usage summary needs a nowcast line expressed as a range rather than a point
figure. Disabling the option must prune the entities from the registry, the way
disabling alerts prunes the alert entities.

## Coordinator notes

The per-endpoint update predicate is the right seam; the nowcast simply gets a
different rule from the fixed-interval one. Note that the set of endpoints to
update is decided for all endpoints before any of them are fetched, so a gate
reading the daily forecast sees the previous tick's copy. At a one-minute tick
against a six-hour window that lag is harmless, but it should be a deliberate
choice rather than an accident.

Coverage for a pre-GA endpoint is unlikely to be global. Mirror the existing
handling for alerts, where a 404 marks the endpoint unsupported for the location
and suppresses the entities rather than erroring.

The on-demand `get_forecast` service should gain a `minute` option — a natural
fit for fetching a nowcast from an automation with polling turned down.

## Unknowns to settle first

- `pageSize` has no documented default or maximum. If the default is small, one
  logical refresh becomes several billed calls and every figure above is wrong.
  Probe with a large `pageSize`, count the segments and check for a
  `nextPageToken` before committing to the cost model.
- Confirm coverage at the target location, and that segment duration is really
  two minutes rather than an artefact of the documentation's example.

## Not in scope

Weather maps (`/v1/mapTypes/...`) is also experimental, but serves binary tiles
for US and European precipitation only. It is a Lovelace overlay, not an entity,
and belongs in its own plan. The `history/hours` endpoint is generally available
and unrelated.
