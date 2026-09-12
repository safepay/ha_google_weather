# Minute forecast captures

Live `GET /v1/forecast/minutes:lookup` responses, kept because the endpoint is
pre-GA and absent from the versioned REST reference: when the shape changes,
these are what the change will be measured against. Reasoning about them lives
in [`../../minute-forecast.md`](../../minute-forecast.md); this directory holds
only the evidence.

Captured 2026-09-12.

## What each one shows

| File | Cadence | Segments | Weather | `nextPageToken` |
| --- | --- | --- | --- | --- |
| `rome-15min-rain-onset-and-cessation.json` | 15 min | 24 | dry, rain 06:30–10:00, dry | empty |
| `chicago-2min-rain-tapering-truncated.json` | 2 min | 132 of 180 | raining, tapering to dry | empty |
| `new-york-2min-default-pagesize.json` | 2 min | 30 | dry | present |
| `paris-15min-full-window.json` | 15 min | 24 | dry | empty |
| `adelaide-15min-uniform-dry.json` | 15 min | 24 | dry | empty |

**`rome-15min-rain-onset-and-cessation.json`** is the most useful file here. A
complete window with a dry leading segment, rain from 06:30 to 10:00 and dry
after, so every derived value has a non-trivial answer: onset is in the future
rather than now, cessation falls inside the window rather than at its edge, and
the accumulation horizons each cut the event at a different point.

**`chicago-2min-rain-tapering-truncated.json`** is the complementary case — rain
already falling at the leading segment, tapering to dry at 06:48.

Between them they settle how `qpf` is quantised, which the plan derived but could
not show directly. Converting each to mm/h — Rome ×4, Chicago ×30 — the two
cadences produce one ladder:

| mm/h | `intensity` | Seen in |
| --- | --- | --- |
| 0.2 | `MID_LIGHT` | both |
| 0.4 | `MID_LIGHT` | both |
| 1.0 | `LIGHT` | both |
| 1.6 | `LIGHT` | both |
| 2.4 | `MID_MODERATE` | Rome |
| 4.0 | `MODERATE` | Rome |

The quantisation is therefore in rate space, not in per-segment millimetres:
Rome's 0.4 mm and Chicago's 0.0133 mm are the same 0.4 mm/h bucket and carry the
same label. `intensity` is a label on that bucket and nothing more, which is why
one `LIGHT` spans two `qpf` values and why reading `qpf` instead loses nothing.

`probability` runs 15–29% in Rome and 29–42% in Chicago across segments in which
rain is *actually falling*, and in Rome it falls as the rate climbs — lowest at
the `MODERATE` peak. Further evidence, from the wet case this time, that the
field is not the chance of rain and that no entity should read it.

**Caveat on Chicago:** truncated. The response declared a window to 12:16 and
only the segments to 10:40 were received. Everything present is the capture; the
missing tail is simply absent rather than filled in.

**`new-york-2min-default-pagesize.json`** is the `pageSize` trap. No explicit
page size was sent, so the response covers one hour — 06:08 to 07:08 of a
six-hour window — and arrives with a page token. It reads as a complete answer
and is one sixth of one.

**`paris-15min-full-window.json`** is a whole window in a single call, and puts
two things beyond argument. Europe gets the coarse cadence: Paris is quarter-
hour, as London and Copenhagen were, so two-minute resolution remains US-only
across everything sampled. And segments do not tile
`overallPredictionTimeframe` — the window runs 06:11 to 12:11 while the segments
run 06:00 to 12:00, overhanging at the start and falling short at the end. Any
code that reads the declared window as the span it actually holds data for is
wrong in both directions.

**`adelaide-15min-uniform-dry.json`** is the same uniform quarter-hour shape
from the third sampled region, and overhangs its window the same way. Worth
being clear about what it is not: the plan records Adelaide returning one big
block plus five quarter-hour segments, and this is not that capture. It is
consistent with the block shape being transient — the same coordinates,
returning the ordinary shape on another day — but a dry uniform response is weak
evidence for that on its own.

## Field shape

Worth stating plainly, because it does not match the rest of this API. The array
is `segments`, not `forecastMinutes`, and `type`, `probability` and `intensity`
sit at the top level of each segment rather than nested under a `precipitation`
object the way `currentConditions` and `forecast/hours` nest theirs. A parser
written by analogy with the other endpoints returns `None` for every field and
reports a permanently dry forecast.

`probability` is a bare number here, not a `{percent, type}` block — and it is
not the chance of rain. See the plan.

## Not captured

Nothing here is reconstructed from the plan's prose: a fabricated sample would be
worse than none, and this plan has twice been wrong by inheriting an inference.
Still wanted, in rough order of value:

- **The Adelaide one-block shape**, ideally the raining pair captured hours
  apart. It is the only evidence that the block shape is transient rather than a
  property of the location, and that is the reason the integration reads what
  arrived instead of classifying anything. The dry uniform capture above does
  not substitute for it.
- **Rain running to the window edge.** Copenhagen forecast rain beginning in its
  final segment, which is the case where cessation must report unknown rather
  than the edge. The Chicago shower stops cleanly inside the window, so nothing
  here covers it.
- **Anything above 4.0 mm/h.** The captures reach `MODERATE`; `MID_HEAVY` and
  `HEAVY`, the top two rungs of the plan's table, rest on readings no longer in
  hand. Nothing here shows whether the buckets continue or the scale is open.
- **Falling snow**, which settles the three open questions under the plan's Snow
  heading and blocks the snow sensors until it exists.
