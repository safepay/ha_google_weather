# Minute forecast captures

Live `GET /v1/forecast/minutes:lookup` responses, kept because the endpoint is
pre-GA and absent from the versioned REST reference: when the shape changes,
these are what the change will be measured against. Reasoning about them lives
in [`../../minute-forecast.md`](../../minute-forecast.md); this directory holds
only the evidence.

Captured 2026-09-12.

## What each one shows

| File | Taken | Cadence | Segments | Weather | `nextPageToken` |
| --- | --- | --- | --- | --- | --- |
| `rome-15min-rain-onset-and-cessation.json` | 06:17 | 15 min | 24 | dry, rain 06:30–10:00, dry | empty |
| `chicago-2min-rain-tapering-truncated.json` | 06:16 | 2 min | 132 of 180 | raining, tapering to dry | empty |
| `chicago-2min-revised-dry-truncated.json` | 06:38 | 2 min | 132 of 180 | dry | empty |
| `chicago-2min-full-window-dry.json` | 07:18 | 2 min | **180** | dry | empty |
| `new-york-2min-default-pagesize.json` | 06:09 | 2 min | 30 | dry | present |
| `paris-15min-full-window.json` | 06:11 | 15 min | 24 | dry | empty |
| `adelaide-15min-uniform-dry.json` | 06:08 | 15 min | 24 | dry | empty |
| `adelaide-15min-repeat-probe-dry.json` | 07:21 | 15 min | 24 | dry | empty |

All times UTC. The three Chicago files are the same location across an hour and
are best read together — see [The Chicago sequence](#the-chicago-sequence).

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

**Caveat on the two truncated Chicago files:** the 06:16 capture declared a
window to 12:16 and only segments to 10:40 were received; the 06:38 one declared
12:38 and reached 11:02. Everything present is the capture and the missing tails
are simply absent, not filled in. The 07:18 capture is complete.

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

**The two Adelaide files** are the same coordinates probed at 06:08 and 07:21,
and both return the ordinary uniform quarter-hour shape, dry, overhanging the
declared window at both ends. Together with Melbourne in the plan they put
Australia firmly at fifteen-minute resolution: no Australian probe has ever
returned the two-minute cadence, which remains US-only across everything sampled.

Worth being clear about what they are not. The plan records Adelaide once
returning one big block plus five quarter-hour segments, and neither of these is
that capture. Two ordinary responses hours apart are consistent with the block
shape being transient, but they are not proof of it.

**`chicago-2min-full-window-dry.json`** is the only capture retained whole, and
the one that settles `pageSize` outright: 180 two-minute segments, a full six
hours, and an empty page token in a single billed call. It is 70 KB, which is
also why the others are partial — a 180-segment response does not survive being
pasted into a terminal, so capture to a file.

It differs from the quarter-hour captures in one respect worth noting: its
segments tile `overallPredictionTimeframe` exactly, 07:18 to 13:18 with no
overhang at either end. Paris and Adelaide overhang at the start and fall short
at the end. So the mismatch is real but not universal, and code still must not
assume either behaviour.

## The Chicago sequence

Three captures from the same coordinates, 06:16, 06:38 and 07:18, and together
they show something no single response can: **the nowcast revises materially
within the window it has already forecast.**

At 06:16 it forecast rain continuing to 06:48, the last three segments at
0.2 mm/h. At 06:38 — inside that same forecast period, with twenty-two minutes
of it still to run — the segments from 06:38 onward read `NONE`. The rain it had
predicted for the following ten minutes was gone. By 07:18 the whole six hours
were dry.

This is the evidence behind polling harder as rain approaches rather than
trusting one response for its full six hours. A dry window is a reliable
guarantee that nothing can *start* soon; a wet one is a current best guess that
can be withdrawn. The schedule treats them asymmetrically for that reason.

It is also a caution for anything that would cache an onset time and act on it
later without re-reading.

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
  than the edge. Both wet captures here stop cleanly inside the window, so
  nothing covers it.
- **Anything above 4.0 mm/h.** The captures reach `MODERATE`; `MID_HEAVY` and
  `HEAVY`, the top two rungs of the plan's table, rest on readings no longer in
  hand. Nothing here shows whether the buckets continue or the scale is open.
- **Falling snow**, which settles the three open questions under the plan's Snow
  heading and blocks the snow sensors until it exists.
