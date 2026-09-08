# Minute forecast (nowcast) support

**Status:** Proposed · **Last reviewed:** 2026-09-08

> Live sampling across four cities shows the endpoint works everywhere tried, at
> two-minute resolution in the US and fifteen-minute in Australia and the UK.
> Response shape varies at the same location over hours, so the implementation
> must read what arrived rather than classify the location; see
> [Regional resolution](#regional-resolution). Always request `pageSize=500` —
> the default returns one sixth of the window. Read `qpf` for every decision;
> `intensity` is derived from it and `probability` is not the chance of rain.

## Objective

Answer two questions the current entities cannot: *when will rain start* and
*how much will fall*. Google's experimental minute forecast endpoint returns a
six-hour precipitation forecast segmented finely enough for both — two-minute
segments where the resolution is best, fifteen-minute where it is not.

## The endpoint

`GET /v1/forecast/minutes:lookup`, on the same host and with the same
`location.latitude` / `location.longitude` / `unitsSystem` parameters the
coordinator already builds for the other weather endpoints, so it needs no new
auth or request plumbing.

Each segment carries a time frame, a precipitation `type` (`NONE`, `RAIN`,
`SNOW`, `HAIL`), a `probability`, a `qpf` quantity, a `snowfallAmount` and an
`intensity`. Onset comes from `type` and `qpf`; accumulation is the raw sum of
`qpf`. Two fields are not what their names suggest — the `intensity` values are
incompletely documented, and `probability` is not the chance of rain — and both
are covered below.

### What a real response looks like

Six live requests across four cities, September 2026, all returning `200 OK`
with a well-formed body and all differing in ways that matter:

| | Melbourne, dry | Adelaide 22:21Z | Adelaide 01:57Z | London | West Virginia | Chicago |
| --- | --- | --- | --- | --- | --- | --- |
| Cadence | block + 5×15m | block + 5×15m | uniform 15m | uniform 15m | uniform 2m | uniform 2m |
| Segments | 6 | 6 | 24 | 24 | 180 | 180 |
| Coverage | partial | partial | full 6h | full 6h | full 6h | full 6h |
| Variation | none, all `NONE` | none, flat 1.0 mm/h | real | real | real | real, full intensity range |

**The window is always six hours. The cadence is not fixed.** Fifteen minutes in
Australia and in London, two minutes in the US. Segment *count* therefore varies
with region — 24 against 180 for the same six hours — so nothing may be
hard-coded to a particular number of segments.

Two-minute resolution is US-only across everything sampled. An earlier draft
expected Europe to match it, by analogy with the US-and-Europe coverage
documented for weather maps; London disproves that. The analogy was never
evidence, and no list of regions should be written into the integration.

**The shape is not a stable property of a location.** The same Adelaide
coordinates returned the one-big-block shape and, three and a half hours later,
uniform quarter-hour segments covering the whole window with genuine variation
in both `qpf` and `probability`. Two earlier readings of this were wrong and are
recorded here so they are not re-derived: the first samples suggested run-length
encoding, which a second sample disproved; the next pair suggested a fixed
degraded structure keyed to region, which this fourth sample disproves in turn.
The block shape is transient, not characteristic.

**Do not classify locations.** An earlier draft proposed probing the response,
deciding supported versus degraded, latching a flag and suppressing the
entities. There is nothing stable to latch: the same coordinates produce both
shapes within hours. Read whatever arrived instead, and let each segment's own
duration carry the precision — a two-minute segment gives genuine minute
accuracy, a quarter-hour segment gives "some time in the quarter hour from
03:15", a five-hour block gives "some time in the next few hours". One code
path, honestly reported, no classification.

**Always send a large explicit `pageSize`.** The parameter is honoured, and it
decides whether a refresh costs one call or six:

| `pageSize` | Segments | Span | `nextPageToken` |
| --- | --- | --- | --- |
| omitted | 30 | 1h | present |
| 100 | 100 | 3h 20m | present |
| 179 | 179 | 5h 58m | present |
| 180 | 180 | 6h — the whole window | **empty** |
| 500 | 180 | 6h | **empty** |

Measured at a two-minute location, where the six-hour window is 180 segments. At
a fifteen-minute location the same window is 24, which fits inside the default
page — which is exactly why an early `pageSize` test against Australian
coordinates appeared to show the parameter did nothing.

**Ask for more than you expect, never an exact count.** 180 is a product of the
current window length and the current cadence, and both are undocumented
behaviour of a pre-GA endpoint that already varies by region. A request pinned
to 180 returns a silently truncated forecast the day either changes. Send
`pageSize=500` and treat a non-empty `nextPageToken` as a broken assumption to
log, not a partial window to act on — the polling design below trusts the span
it was given.

The default is a trap for the same reason: thirty segments with a page token
looks like a complete answer and is one sixth of one.

**Do not generalise this from the other endpoints, or to them.** `forecast/hours`
caps at 24 results per page whatever `pageSize` asks for — `pageSize=300`
returns 24 — which is why its full 240-hour window costs ten calls and why
issue #64 is closed as not worth the budget. `forecast/minutes` honours
`pageSize` to at least 500. Same API, same parameter, opposite behaviour.
Reasoning about one from the other gives the wrong answer in both directions,
so the nowcast's one-call cost model must not be assumed to extend anywhere
else.

### qpf is quantised, and intensity is derived from it

The documented `intensity` values are `PRECIPITATION_INTENSITY_UNSPECIFIED`,
`NO_INTENSITY`, `LIGHT`, `MODERATE` and `HEAVY`. Live responses also return
`MID_LIGHT`, `MID_MODERATE` and `MID_HEAVY`, none of which are documented.

Converting every observed `qpf` to mm/h — multiply by 30 for two-minute
segments, by 4 for fifteen-minute — gives a mapping that holds across four
cities and both cadences:

| mm/h | `intensity` | Observed in |
| --- | --- | --- |
| 0 | `NO_INTENSITY` | all |
| 0.2 | `MID_LIGHT` | Adelaide, West Virginia, Chicago |
| 0.4 | `MID_LIGHT` | Adelaide, West Virginia, London, Chicago |
| 1.0 | `LIGHT` | Adelaide, West Virginia, London, Chicago |
| 1.6 | `LIGHT` | London, Chicago |
| 2.4 | `MID_MODERATE` | London, Chicago |
| 4.0 | `MODERATE` | Chicago |
| 7.0 | `MID_HEAVY` | Chicago |
| 15.0 | `HEAVY` | Chicago |

A single tapering shower in Chicago walked down every rung in order, which
confirms the ordering outright rather than by inference. `MID_` marks a step
*between* the previous named level and this one, so `MID_LIGHT` is lighter than
`LIGHT`:

```text
NO_INTENSITY < MID_LIGHT < LIGHT < MID_MODERATE < MODERATE < MID_HEAVY < HEAVY
```

That is the complete set. A `MID_` variant exists only where there is a gap to
sit in, and there is nothing below `NO_INTENSITY` for a `MID_NO_INTENSITY` to
occupy.

**`qpf` is quantised.** Those mm/h figures are the only values seen anywhere —
eight discrete rates with nothing in between, identical across four cities and
both cadences. `qpf` is not a continuous forecast quantity but a bucket.

**`intensity` therefore carries no information that `qpf` does not.** It is a
label on the bucket, a pure function of the rate. Read `qpf` for every decision
and treat `intensity` as display only; an unrecognised value then costs nothing,
because the number behind it is still there. This is a stronger guarantee than
the usual advice to guard an open enum — there is genuinely nothing to lose.

It also confirms, independently of the hourly comparison below, that `qpf` is a
per-segment total rather than a rate. Read as a rate, Chicago's `HEAVY` segments
would be 0.5 mm/h, which is drizzle; as a per-segment total they are 15 mm/h,
which is heavy rain. Two unrelated lines of evidence agree.

**`PRECIPITATION_INTENSITY_UNSPECIFIED` is not a rung on this ladder.** It is
the protobuf zero value, meaning the field was never set, and it must not be
conflated with `NO_INTENSITY`, which is a real reading of no precipitation.
Treat it as unknown — neither dry nor wet — and fall back to `qpf` and `type`.

Never rank these by name and never map from a closed set. An unrecognised value
must render as unknown rather than defaulting to either end of the scale, the
same failure that produced the missing snow icons: a new condition needs both an
icon and a state, or it renders as unknown.

### qpf sums directly; probability does not mean chance of rain

The London nowcast and the hourly forecast were captured for the same location
and the same six hours, which settles how `qpf` should be aggregated. Summing the
nowcast's per-segment `qpf` within each hour, against that hour's forecast `qpf`:

| Hour (UTC) | Nowcast Σ`qpf` | Hourly `qpf` | Ratio | Nowcast probability | Hourly probability |
| --- | --- | --- | --- | --- | --- |
| 02 | 0.70 | 0.729 | 0.96 | 27–46% | 70% |
| 03 | 1.15 | 1.047 | 1.10 | 18–39% | 80% |
| 04 | 1.80 | 1.305 | 1.38 | 12–23% | 85% |
| 05 | 2.40 | 1.359 | 1.77 | 12–13% | 86% |
| 06 | 2.40 | 1.184 | 2.03 | 10–13% | 79% |
| 07 | 1.60 | 0.868 | 1.84 | 12–17% | 65% |
| **Total** | **10.05** | **6.49** | **1.55** | | |

**Sum `qpf` raw. Do not weight it by `probability`.** Weighting gives 1.7 mm
against the hourly endpoint's 6.49, understating by roughly four times. The raw
sum comes to 1.55× overall and matches almost exactly in the near-term hours,
which is where a nowcast is most trustworthy. Treating `qpf` as a rate rather
than a per-segment total was also checked and gives 0.24–0.44×, which is clearly
wrong.

The residual 1.55× is disagreement between two different forecast systems, not
an error to correct. Note its shape: the first two hours agree within 10% and
the divergence grows with lead time, which is what radar-extrapolation nowcasting
against numerical weather prediction is expected to look like. Do not try to
reconcile them, and do not blend them.

**The nowcast's `probability` is not the chance of rain, and is not comparable
to the hourly endpoint's.** For the same hours the hourly forecast reports 65–86%
while the nowcast reports 10–13%, and the two move in opposite directions: as
hourly probability and `qpf` both rise, nowcast probability falls. A field that
drops while rainfall rises is measuring something else — confidence, or the
likelihood of a particular intensity class — and its meaning is undocumented.

Three rules follow:

- **Derive onset from `type` and `qpf`, not from `probability`.** Those two
  behave exactly as expected across every sample: `NONE` with `qpf` 0 when dry,
  `RAIN` with positive `qpf` when wet. This replaces an earlier proposal in this
  plan to pick a probability threshold, which would have been arbitrary at best:
  nothing in the London sample exceeds 46%, so a `probability > 50%` rule would
  have reported no rain at all across six continuous hours of it peaking at
  2.4 mm/h.
- **Never share a threshold between the two endpoints.** The polling gate reads
  hourly probability and sits on a 65–86% scale; anything reading nowcast
  probability sits on a 10–46% one. A single configured percentage cannot serve
  both.
- **Surface the nowcast probability as an attribute at most, never as the basis
  of a binary sensor**, until its meaning is established.

### Other findings

- **Segments need not tile `overallPredictionTimeframe`.** In several samples
  the first began up to an hour in the *past* and the last ended short of the
  declared window. Clamp to the present, and never read "no wet segment found"
  as "dry for the whole window".

The endpoint is **Experimental (pre-GA)**. It is absent from the versioned REST
reference, the API FAQ still claims nowcasting is not offered at all, and both
the documented segment cadence and the intensity enum disagree with what the API
returns. Treat the shape as unstable and guard every read, more strictly than
for the GA endpoints.

## Regional resolution

Resolution differs by region: fifteen minutes in Australia and London, two
minutes in the US. Only the US sample has shown the fine cadence, and the
boundary is undocumented — the US-and-Europe coverage documented for weather
maps does not apply, since London gets the coarse one.

This affects how good the feature is, not whether it works. A quarter-hour
onset time still answers the question this plan exists to answer; two-minute
resolution answers it better. Since precision travels with each segment, both
are served by the same implementation with no branching, and a region whose
resolution improves later simply starts producing better answers.

What must not happen is a coarse response being reported as though it were
precise. That is handled where the entities are described, by publishing the
segment duration alongside the onset time.

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

**The cap may never exceed the span the last response actually covered.** That
is the invariant the whole design rests on, and it is why `pageSize` is a
requirement rather than an optimisation: at the default the horizon is one hour
and the dry cap would have to stay under about fifty minutes, whereas
`pageSize=500` buys a six-hour guarantee for the same single call. Ask for the
whole window, then cap at around two hours — comfortably inside it, with margin
for convection developing mid-window.

This was chosen over a fixed day/night interval pair, as used by the other
endpoints, for two reasons. The day/night split suits data whose *value* varies
by time of day, which does not describe rain onset — arguably it matters more
overnight. And a fixed interval spends calls uniformly, whereas the whole cost
problem is that calls are only worth making as rain approaches.

An intermediate "armed" tier polling every 20 minutes was considered and
rejected: with a dry response already guaranteeing six dry hours, it buys little
onset precision for several hundred calls a month.

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

With the whole six-hour window fetched in one call, a two-hour dry cap and a
three-minute floor cost roughly **1,260 calls a month** in a temperate climate:
about twenty dry days, plus ten carrying a few hours of rain each. That fits
inside even the smallest headroom above, so the nowcast never *requires* giving
anything up — though turning hourly forecasts off remains the natural trade for
anyone who wants more margin.

Note what the table does *not* imply: surplus headroom cannot usefully be spent
here. The dry cap is bounded above by the six hours a response covers and below
by diminishing returns — under about fifteen minutes it is re-fetching a
forecast that has barely changed. That confines any sensible configuration to
roughly 1,200–2,400 calls a month regardless of how much headroom exists.
Surplus is better given to current conditions, which genuinely improves with
frequency.

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

- minutes until precipitation starts (duration), from the first segment whose
  `type` is not `NONE`
- expected precipitation over the next 60 minutes (precipitation depth), the raw
  sum of `qpf` across those segments
- minutes until precipitation stops (duration)
- a binary sensor for precipitation expected within the next hour

None of these read `probability`, which does not mean what its name suggests.

Derived values should be computed at fetch time in the coordinator and cached,
following the existing 24-hour snow total, so the sensors stay simple lookups.

Do not attach all the raw segments to a state attribute. A two-minute region
returns 180 objects per refresh and the recorder re-serialises attributes on
every state change. Downsample to fifteen-minute buckets for display, or keep
the segments out of the recorder entirely and expose only the derived scalars.

**Onset precision must not be overstated, and this carries the whole
regional-variation problem.** The sensor's value comes from a segment's
`startTime`, and that segment may be two minutes wide, fifteen, or — in the
transient block shape — several hours. Publish the segment's duration alongside
the onset time so the resolution is visible rather than implied.

Getting that right is what makes classification unnecessary. A coarse response
then degrades the *answer* rather than breaking the feature, and there is no
flag to latch, no region list to maintain, and nothing to go stale when Google
changes coverage.

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

Do not copy the `alerts_supported` pattern here. A tri-state supported flag
suits a binary, stable condition; nowcast resolution is neither, since the same
coordinates returned both a coarse and a fine response within hours. There is no
capability to latch — parse what arrived and report its precision honestly. See
[Regional resolution](#regional-resolution).

Whether the endpoint should ever stop polling itself is a separate question from
resolution, and there is no evidence yet of a response that justifies giving up.
Leave it out until one is observed.

The on-demand `get_forecast` service should gain a `minute` option — a natural
fit for fetching a nowcast from an automation with polling turned down.

## Unknowns to settle first

**Settled.** The endpoint returns a usable six-hour forecast in both sampled
regions — two-minute segments in the US, fifteen-minute in Australia — with
genuine variation in `qpf` and `probability` in each. Shape is not a stable
property of a location, so nothing may be classified or latched. `pageSize=500`
returns the whole window in one call with an empty page token, so a refresh is
one billed call and the cost model above stands.

Nothing blocks a first implementation.

Aggregation is settled too: `qpf` sums raw, verified against the hourly
forecast for the same London hours. `probability` is not the chance of rain and
no entity should read it. Both are set out above.

**Still open, and none of it blocking.**

- What produces the occasional one-block response. Both shapes have come from
  the same Adelaide coordinates hours apart, so it is transient, but its cause
  is unknown. Parsing must handle it; nothing needs to predict it.
- Where fine resolution is actually available. Only the US has shown two-minute
  segments; Australia and London both give fifteen. Changes nothing structural,
  since precision is read per segment.
- What the nowcast's `probability` actually measures. It falls as `qpf` rises
  and sits on a different scale from the hourly endpoint's, so it is not the
  chance of rain. Nothing depends on the answer while no entity reads it, but it
  would be worth knowing before anything ever does.
- Whether a `qpf` floor is needed for onset, so that a trace of drizzle does not
  announce incoming rain. `type` alone may be enough; the quantised rate ladder
  makes a threshold easy to place if not, since 0.2 mm/h is the lowest non-zero
  bucket.
- Whether the eight observed rates are the complete set. They are consistent
  across four cities, but nothing above 15 mm/h has been seen and the buckets
  may be wider than the observed values suggest.

## Not in scope

Weather maps (`/v1/mapTypes/...`) is also experimental, but serves binary tiles
for US and European precipitation only. It is a Lovelace overlay, not an entity,
and belongs in its own plan. The `history/hours` endpoint is generally available
and unrelated.
