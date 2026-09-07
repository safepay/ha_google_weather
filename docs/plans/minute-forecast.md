# Minute forecast (nowcast) support

**Status:** Proposed, regionally limited · **Last reviewed:** 2026-09-08

> Live sampling shows the real nowcast is available in the US but not in
> Australia, where the endpoint returns a degraded response over `200 OK`. The
> feature needs a runtime capability check; see
> [Regional availability](#regional-availability). One call returns one hour,
> not six.

## Objective

Answer two questions the current entities cannot: *when will rain start* and
*how much will fall*. Google's experimental minute forecast endpoint returns
precipitation in two-minute segments — one hour of them per call, against a
six-hour model horizon — which is the right resolution for both.

## The endpoint

`GET /v1/forecast/minutes:lookup`, on the same host and with the same
`location.latitude` / `location.longitude` / `unitsSystem` parameters the
coordinator already builds for the other weather endpoints, so it needs no new
auth or request plumbing.

Each segment carries a time frame, a precipitation `type` (`NONE`, `RAIN`,
`SNOW`, `HAIL`), a `probability`, a `qpf` quantity, a `snowfallAmount` and an
`intensity` (`NO_INTENSITY`, `LIGHT`, `MODERATE`, `HEAVY`). Onset is the first
non-`NONE` segment; accumulation is the sum of `qpf` over a window.

### What a real response looks like

Three live requests, September 2026, within minutes of each other. They differ
so sharply that the endpoint is best understood as two different services behind
one URL.

| | Melbourne (dry) | Adelaide (wet) | West Virginia (wet) |
| --- | --- | --- | --- |
| Segments | 6 | 6 | 30 |
| Cadence | 1 block + 5×15m | 1 block + 5×15m | 2 minutes, uniform |
| Span covered | 6h 45m | 6h 45m | exactly 1h |
| First segment | starts 1h in the past | starts 1h in the past | starts at `startTime` |
| `nextPageToken` | empty | empty | **populated** |

**The Australian responses are a degraded tier.** Both returned identical
segment boundaries — one block covering 21:15–02:45, then five quarter-hour
segments to 04:00 — despite different cities and opposite weather. Segmentation
there is a fixed structure carrying no information. An earlier draft proposed
these were run-length encoded, with granularity following the data; the two
samples together disprove it.

**The US response is the real product.** Thirty two-minute segments tiling
contiguously from `startTime`, with genuine variation: probability drifting
43→36%, `qpf` stepping 0.0133→0.0067 mm (0.4 down to 0.2 mm/h), and a clean edge
where `RAIN` gives way to `NONE` at 23:00. That last is exactly the signal this
plan exists to surface — "rain stops in 36 minutes", stated by the data.

This confirms regional tiering, matching the US-and-Europe limit already
documented for weather maps. Two consequences follow, and both matter more than
the resolution difference itself.

**Degradation is invisible at the HTTP layer.** Australia returns `200 OK` with
a well-formed body. The `alerts_supported` pattern, which keys off a 404, cannot
be reused directly — support has to be inferred by inspecting the response.
Segment count and the duration of the first segment are the discriminators: a
handful of segments, the first of them hours long, means the nowcast is not
really available.

**A page is one hour, not six.** The US response covers 22:24–23:24 and hands
back a `nextPageToken` for the rest. The six-hour `overallPredictionTimeframe`
is the *model's* horizon, not what one call returns. Thirty segments looks like
a default page size, so the full window is plausibly six calls.

This corrects an earlier conclusion in this document. "One refresh is one billed
call" was generalised from the Australian samples, whose token was empty only
because six segments was all they had. For the same reason the `pageSize` test
run against an Australian location proved nothing about pagination: there was
nothing further to return. **Whether `pageSize` raises the segments-per-call at a
supported location is now the open question the cost model depends on.**

Other findings from the samples:

- **`intensity` returned `MID_LIGHT`** in both wet responses, which is not among
  the documented values (`NO_INTENSITY`, `LIGHT`, `MODERATE`, `HEAVY`). The enum
  is open; do not map it from a closed set.
- **`type` is `RAIN` at 36–43% probability**, and at 20–22% in the Adelaide
  sample. Treating any non-`NONE` segment as onset would announce rain on a
  one-in-five chance. Onset needs a probability threshold, not a type check.
- **Segments need not tile `overallPredictionTimeframe`.** In the degraded
  responses the first began an hour in the past and the last ended twenty
  minutes short of the declared window. Clamp to the present, and never read "no
  wet segment found" as "dry for the whole window".

The endpoint is **Experimental (pre-GA)**. It is absent from the versioned REST
reference, the API FAQ still claims nowcasting is not offered at all, and both
the documented segment cadence and the intensity enum disagree with what the API
returns. Treat the shape as unstable and guard every read, more strictly than
for the GA endpoints.

## Regional availability

The feature is worth building, but only where the real nowcast exists. Elsewhere
the response supports nothing the daily forecast does not already provide — a
flat 1.0 mm/h smear across four and a half hours, which is an absence of
information rather than a coarse version of it.

So the endpoint needs a **runtime capability check**, in the spirit of
`alerts_supported` but keyed on content rather than status: after the first
fetch, judge whether segments are fine-grained enough to be useful, and if not,
suppress the entities and stop polling. Getting this right matters more than
usual, because a user in a degraded region who is not detected pays for calls
that can never tell them anything.

Two practical consequences to accept openly:

- The maintainer cannot dogfood this. Development and support would be for a
  feature that only functions in regions the maintainer cannot observe from, so
  the capability check and the parser both need to be defensive by construction
  rather than by testing.
- Regional coverage is undocumented and will change. The check must re-evaluate
  periodically rather than latching permanently, so that regions gaining support
  later start working without user intervention.

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

The decisive property is that a response is a **lookahead, not a snapshot**. A
page showing `NONE` across every segment is a guarantee that rain cannot begin
for the span that page covers — so it is also a licence not to poll until near
the end of it. Polling frequency should therefore be derived from the data
already in hand:

```text
sleep = clamp(minutes_until_first_wet_segment / 2, floor, cap)
```

with a floor of about 3 minutes and a cap that depends on whether rain is
expected at all (below). Precipitation already falling pins it to the floor.

**The horizon is one hour, not six.** An earlier draft of this plan built the
caps around a six-hour guarantee, before sampling showed that a single call
returns one hour and hands back a page token for the rest. The scheme is
unchanged in shape, but every cap must now fit inside the span actually
fetched — a dry cap somewhere under 50 minutes, leaving margin, rather than the
two hours previously proposed. Do not let a cap exceed the coverage of the last
response; that is the invariant the whole design rests on.

Paging further out to extend the horizon is possible but rarely worth it. Each
page is another billed call, and a second hour of two-minute detail answers a
question — will it rain late this afternoon — that the hourly forecast already
answers for free.

This was chosen over a fixed day/night interval pair, as used by the other
endpoints, for two reasons. The day/night split suits data whose *value* varies
by time of day, which does not describe rain onset — arguably it matters more
overnight. And a fixed interval spends calls uniformly, whereas the whole cost
problem is that calls are only worth making as rain approaches.

An intermediate "armed" tier polling every 20 minutes was considered and
rejected: with a dry page already covering the next hour, it buys little onset
precision for several hundred calls a month.

## What the gate reads: hourly where available, daily otherwise

The cap is set from precipitation probability in a forecast the coordinator has
already fetched and paid for — no extra calls either way.

**Prefer the hourly forecast when it is enabled.** Its lookahead can be trimmed
to the next hour or two — roughly what a nowcast page covers — so the cap
tightens for the specific window rain is expected in and stays loose the rest of
the day. A daily block probability cannot do that: forty per cent across a
sixteen-hour daytime block holds the cap tight from breakfast onwards for rain
that arrives at six in the evening.

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
hour a page covers — the one case the nowcast's own guarantee does not cover —
and an hourly signal tightens it when that development is actually likely,
rather than across a whole daylight block.

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

The one-hour page horizon sets the cost, because it caps how long the integration
may wait between calls. A 45-minute dry cap with a three-minute floor, in a
temperate climate with rain falling perhaps 5% of the time, comes to roughly
**1,600 calls a month** — about 900 from dry-weather polling and 700 from the
floor during rain.

This is a correction. An earlier draft put the figure at 1,260 using a two-hour
dry cap, which the six-hour horizon appeared to permit; one hour per call does
not. The consequence is that the nowcast no longer fits the top row of the
table. With every other endpoint at its default, adding it runs a couple of
hundred calls over the free tier, so something must give — and turning hourly
forecasts off, which frees 1,680, is by far the most natural thing to give. On
the second row it fits with room to spare.

Note also what the table does *not* imply: surplus headroom cannot be spent
here. The dry cap is bounded above by the hour a page covers and below by
diminishing returns — under about fifteen minutes it is re-fetching a forecast
that has barely changed. That confines any sensible configuration to roughly
1,500–2,400 calls a month regardless of how much headroom exists. Surplus is
better given to current conditions, which genuinely improves with frequency.

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

Attaching the raw segments as a state attribute is fine. An earlier draft called
for downsampling them, assuming ~180 objects per response; a supported-region
page holds thirty, which the recorder will not notice. Revisit only if raising
`pageSize` turns out to multiply that.

Onset precision must not be overstated. The sensor's value comes from a
segment's `startTime`. In a supported region that is a two-minute window and the
precision is real; in a degraded one it may be five hours wide. Report the onset
time as given and expose the segment's duration alongside it, so the resolution
is visible rather than implied — and rely on the capability check to keep the
degraded case from producing entities at all.

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
sees the previous tick's copy of whichever forecast it reads. At a one-minute
tick against an hour of coverage that lag is harmless, but it should be a
deliberate choice rather than an accident.

Support is regional, and — unlike alerts — it is not signalled by a 404. The
alerts handling is the right *shape* to copy: a tri-state supported flag, checked
before the endpoint is polled and before entities are created. The test itself
must be different, judging the response body rather than the status code. See
[Regional availability](#regional-availability).

Note also the bug that pattern currently has: `alerts_supported` suppresses the
entities but is never consulted when building the endpoint list, so an
unsupported location keeps paying for 404s. Do not reproduce that here — a
degraded response must stop the polling, not just hide the sensors.

The on-demand `get_forecast` service should gain a `minute` option — a natural
fit for fetching a nowcast from an automation with polling turned down.

## Unknowns to settle first

**Settled.** The real nowcast exists and is regional: US coordinates return
thirty uniform two-minute segments with genuine variation, Australian ones a
degraded six-segment response over `200 OK`. Degradation is not signalled by
status code. A page covers one hour and carries a `nextPageToken` for the rest,
so a refresh is one call per hour of lookahead, not one call for six.

**Blocking, and cheap.** Re-run the `pageSize` test against a *supported*
location. The earlier test used Australian coordinates, where six segments was
everything available, so it demonstrated nothing about pagination. Thirty
segments looks like a default page size; if `pageSize` raises it, a longer
horizon costs one call instead of several and several caps in this plan can be
loosened. This is the last input the cost model needs.

**Still open.**

- Whether the degraded response's structure is fixed or clock-quantised. The two
  Australian samples were five minutes apart and cannot distinguish the two.
  Sample again hours later — it decides how the capability check should be
  written.
- Where the boundary of the supported region actually falls. Europe is
  documented as supported for weather maps and is untested here. The capability
  check must be derived from the response rather than from any list of regions.
- The full `intensity` enum, given `MID_LIGHT` already sits outside the
  documented set. Collect values rather than guessing the pattern.
- A sensible probability threshold for onset, given `RAIN` is reported at 20% in
  one sample and 36–43% in another, in the latter case while rain was falling.

## Not in scope

Weather maps (`/v1/mapTypes/...`) is also experimental, but serves binary tiles
for US and European precipitation only. It is a Lovelace overlay, not an entity,
and belongs in its own plan. The `history/hours` endpoint is generally available
and unrelated.
