# Minute forecast (nowcast) support

**Status:** On hold · **Last reviewed:** 2026-09-08

> Live responses from two Australian cities carry no time resolution in the next
> four and a half hours, which is the period this feature exists to describe.
> Do not start building until the US comparison in
> [Blocking problem](#blocking-problem-no-near-term-resolution) is run.

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

### What a real response looks like

Two live requests, September 2026, five minutes apart: Melbourne in dry weather
and Adelaide in wet. Both returned **six segments, not the ~180 a two-minute
cadence implies**, and an empty `nextPageToken`. A refresh is genuinely one
billed call, and the cost model below holds. `pageSize` had no effect on either.

Both returned **identical segment boundaries** despite different locations and
opposite weather:

| Segment | Span | Duration |
| --- | --- | --- |
| 1 | 21:15 → 02:45 | 5h 30m |
| 2–6 | 02:45 → 04:00 | 15m each |

So segmentation is a **fixed structure, not driven by the data**. An earlier
draft of this plan proposed that responses were run-length encoded, with
granularity sharpening where something was happening; the wet sample disproves
it. The wet response carried `RAIN` in every segment and was shaped exactly like
the dry one.

Also observed:

- **Segments do not tile `overallPredictionTimeframe`.** Melbourne's declared
  window was 22:16–04:16, and its segments ran 21:15–04:00. The first began an
  hour in the *past*, and the last twenty-odd minutes of the window had no
  segment. Clamp to the present when computing onset, and never read "no wet
  segment found" as "dry for the whole window".
- **`intensity` returned `MID_LIGHT`**, which is not among the documented
  values (`NO_INTENSITY`, `LIGHT`, `MODERATE`, `HEAVY`). The enum is open. Do
  not map it from a closed set; unknown values must degrade gracefully.
- **`type` was `RAIN` at 20–22% probability.** Treating any non-`NONE` segment
  as onset would fire on a one-in-five chance. Onset needs a probability
  threshold, not a type check alone.

The endpoint is **Experimental (pre-GA)**. It is absent from the versioned REST
reference, the API FAQ still claims nowcasting is not offered at all, and the
documented segment cadence and intensity enum both disagree with what the API
actually returns. Treat the shape as unstable and guard every read, more
strictly than for the GA endpoints.

## Blocking problem: no near-term resolution

The fixed structure puts the detail in the wrong place. The Adelaide request was
made at 22:21Z and segment 1 ran to 02:45Z, so **the next four and a half hours
came back as one undifferentiated block**. The only fine detail covered
02:45–04:00 — between 4.4 and 5.6 hours ahead.

That is backwards for a nowcast, and it defeats the objective at the top of this
document. For "when will rain arrive", the near term is the whole question, and
there is no time resolution in it. The most such a response can support is *"22%
chance of rain, 5.5 mm, somewhere in the next four and a half hours"* — which
the daily forecast already provides, at no additional cost.

The `qpf` figures confirm the block carries no internal structure: 5.5 mm across
5.5 hours in segment 1, and 0.25 mm across each 15-minute segment, are both
exactly 1.0 mm/h. The block is a flat smear at the same uniform rate, not a
summary of anything varying.

**Most likely a degraded regional tier.** Google's documented example, which
does show two-minute segments, uses coordinates in West Virginia. The weather
maps endpoint is explicitly US and Europe only. The high-resolution nowcast
model is plausibly limited the same way, with other regions receiving a
synthesised fallback.

This is cheap to settle: request the documentation's own US coordinates
(`37.60451, -80.59044`) with the same key and compare. Two-minute segments there
means the resolution is regional and Australian users gain nothing from this
endpoint. The same six-segment shape means the documented example is stale and
the endpoint is like this everywhere.

Until that is answered, the rest of this plan is contingent. The polling design
below still holds — a dry block is still a usable guarantee — but the product it
would deliver in this region is not worth the calls.

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

Attaching the raw segments as a state attribute is fine. An earlier draft of
this plan called for downsampling them, on the assumption of ~180 objects per
response; the observed count is single figures, so there is nothing to
downsample and the recorder has nothing to complain about. Revisit only if a
wet-weather sample turns out to be very much larger.

Onset precision must not be overstated. The sensor's value comes from a
segment's `startTime`, and that segment may be fifteen minutes wide — or five
hours, in the merged dry case. Reporting "rain in 7 minutes" off the front edge
of a fifteen-minute block invents precision the data does not carry. Report the
onset time as given and expose the segment's duration alongside it, so the
resolution is visible rather than implied.

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

**Settled.** A plain request returns the whole window in one page with an empty
`nextPageToken`, so a refresh is one billed call and the cost model stands.
`pageSize` changes nothing. The endpoint responds for Australian coordinates, so
this is not a coverage 404. A wet-weather sample has been captured, and it is
shaped identically to a dry one.

**Blocking.** Request `37.60451, -80.59044` — the documentation's own US
coordinates — and compare the segment structure. This decides whether the
feature is worth building at all; see [Blocking
problem](#blocking-problem-no-near-term-resolution).

**Still open, if the US test is favourable.**

- Whether the near-term block shortens as the model's confidence window moves,
  or is always roughly the next four to five hours. Two samples taken five
  minutes apart cannot distinguish a fixed structure from a clock-quantised one;
  sample again several hours later.
- The full `intensity` enum, given that `MID_LIGHT` is already outside the
  documented set. Collect values over time rather than guessing at the pattern.
- A sensible probability threshold for onset, given `RAIN` is reported at 20%.

## Not in scope

Weather maps (`/v1/mapTypes/...`) is also experimental, but serves binary tiles
for US and European precipitation only. It is a Lovelace overlay, not an entity,
and belongs in its own plan. The `history/hours` endpoint is generally available
and unrelated.
