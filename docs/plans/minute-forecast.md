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

## What the gate reads: hourly where available, daily otherwise

The cap is set from precipitation probability in a forecast the coordinator has
already fetched and paid for — no extra calls either way.

**Prefer the hourly forecast when it is enabled.** Its lookahead can be trimmed
to exactly the six hours the nowcast itself covers, so the cap tightens for the
specific window rain is expected in and stays loose the rest of the day. A daily
block probability cannot do that: forty per cent across a sixteen-hour daytime
block holds the cap tight from breakfast onwards for rain that arrives at six in
the evening.

**Fall back to the daily forecast when hourly is disabled.** Hourly forecasts
are user-optional, and turning them off is exactly what frees the headroom the
nowcast needs, so the users most likely to run this feature are
disproportionately the ones with no hourly data to gate on. A gate that only
understood hourly would be unavailable to its own audience. Daily forecasts are
hard-coded on in both the config and options flows, so `daytimeForecast` /
`nighttimeForecast` precipitation probability is always there to fall back to.

This is one predicate with two sources, not two code paths and not a
configuration dependency: read hourly if present, else daily. Nothing in the
config flow needs to couple the two options together, and disabling hourly later
must degrade the gate rather than break it.

Be honest about the size of the gain. Preferring hourly saves a few hundred
calls a month at most, because the cost is dominated by time spent at the floor
while rain is actually falling, and no gate affects that. The real benefit is
responsiveness: the cap exists to catch convection that develops *inside* the
six-hour window — the one case the nowcast's own guarantee does not cover — and
an hourly signal tightens it when that development is actually likely, rather
than across a whole daylight block.

Two further signals are free and should feed the same predicate: current
conditions already reporting rain should go straight to the floor, and
`thunderstormProbability` — present on both the hourly and the daily blocks —
should tighten the cap even when rain probability is low, since convective
showers are the case forecast guidance most often misses and radar nowcasting
handles best.

## Estimated cost

Headroom against the 10,000-call free tier depends on what else is enabled:

| Configuration | Spent | Headroom |
| --- | --- | --- |
| Defaults, everything on | 8,640 | 1,360 |
| Hourly forecasts off (−1,680) | 6,960 | 3,040 |
| Hourly and alerts off (−2,400) | 4,560 | 5,440 |

A conservative configuration — a three-minute floor, a two-hour cap on dry days
— costs roughly 1,260 calls a month in a temperate climate: about twenty dry
days, plus ten carrying a few hours of rain each. That fits inside even the
smallest of those, so the nowcast never *requires* giving anything up. With
hourly off, a two-minute floor and a one-hour dry cap lands near 1,800.

Note what the table does *not* imply. Extra headroom does not convert into
proportionally more useful polling, because a dry response already guarantees
six dry hours — shortening the dry cap only buys earlier notice of newly
developed convection, and its value falls away fast. Past roughly 2,000 calls a
month the nowcast has nothing worthwhile left to spend on, and surplus headroom
is better given to current conditions, which genuinely improves with frequency.

Alerts are the wrong thing to trade. Hourly forecasts are a convenience the
nowcast largely supersedes for short-range rain, so swapping them is a real
upgrade; alerts are safety-critical, and turning them off to fund a rain timer
is a bad exchange that the documentation should not encourage. The 5,440 row
describes users whose region has no alert coverage at all, more than it
describes a configuration to recommend.

Worth saying plainly in the user documentation: for the question this plan
exists to answer, the nowcast is strictly better than the hourly forecast, and
the two compete for one budget. Trading hourly for the nowcast is an upgrade for
short-range rain timing. What it costs is the ten-day hourly outlook, the hourly
forecast on the weather entity, and the 24-hour snow total, which is derived
from hourly entries and would go unavailable with them.

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
update is decided for all endpoints before any of them are fetched, so the gate
sees the previous tick's copy of whichever forecast it reads. At a one-minute tick
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
