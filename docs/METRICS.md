# Metrics

## Metrics are rows, not functions

"Fastball max velocity" is a row in `metric_definitions`. No Python function, no
React component and no API endpoint names it. The coach will change this set
repeatedly, and the alternative — a hardcoded calculation per metric — makes
every change a deployment.

## Anatomy of a definition

| Field | Purpose |
|---|---|
| `key` | Stable dotted identifier (`pitch.fastball.max_velocity`). What code, mappings and API callers refer to. |
| `display_name` | What a coach reads. Free to change without breaking anything. |
| `event_source` | `PITCH` or `HIT` — which normalized table feeds it. |
| `aggregation` | `MAX · MIN · AVG · SUM · COUNT · RATE` |
| `unit` | Canonical unit. **`NOT NULL`.** |
| `record_direction` | `HIGHER_IS_BETTER · LOWER_IS_BETTER · NONE` |
| `min_sample_size` | Minimum qualifying events before the metric is calculated at all. |
| `spec` | The selector — which events, filtered how. |
| `calculation_version` | Bumped by hand when the formula changes meaning. |
| `is_headline` | Shown on the overview without being asked for. |

## The `spec` vocabulary

Deliberately tiny, and **not** a query language:

```jsonc
{
  "field": "velocity_mph",                       // what to aggregate (omit for COUNT)
  "filters": [                                   // which events qualify
    { "field": "pitch_type", "op": "eq", "value": "FASTBALL" }
  ],
  "numerator_filters": [ ... ],                  // RATE only
  "context_dimensions": { "pitch_type": "FASTBALL" },  // labels for the UI
  "min_value": 40.0,                             // range guards
  "max_value": 105.0,
  "round_to": 1
}
```

Operators: `eq · neq · in · gt · gte · lt · lte · is_true · is_not_null`.

It can express what a coach-editable metric needs and little else. Anything
requiring real expressiveness should become a **new named aggregation with a
test**, not a more powerful DSL nobody can reason about.

Training context is addressable as `ctx.<key>` — so `{"field": "ctx.drill", "op":
"eq", "value": "Velo Block"}` already works, without a schema change. That is the
groundwork for Phase 8.

## Rules the engine enforces

**Missing is not zero.** A pitch with no spin reading contributes nothing to
average spin rather than dragging it toward zero.

**Below minimum sample returns nothing, not zero.** `calculate()` returns `None`
when a metric does not apply. "No data" and "a value of zero" are different
claims and are never conflated — in the database, the API, or the UI (which shows
`—`).

**Out-of-range readings are excluded from the sample too.** An implausible value
was never credible evidence, so it does not inflate `n` either.

**Filters exclude events from the sample as well as the value.** A slider is not
weak evidence about fastball velocity; it is no evidence, and `n` says so.

## The starter set

Nine metrics, chosen to prove the architecture rather than to be final. The coach
is expected to change them.

### Pitching

| Key | Aggregation | Unit | Record | Min n |
|---|---|---|---|---|
| `pitch.fastball.max_velocity` | MAX `velocity_mph`, fastballs | mph | ↑ | 3 |
| `pitch.fastball.avg_velocity` | AVG `velocity_mph`, fastballs | mph | ↑ | 5 |
| `pitch.fastball.avg_spin_rate` | AVG `spin_rate_rpm`, fastballs | rpm | — | 5 |
| `pitch.strike_percentage` | RATE of strikes | % | ↑ | 10 |
| `pitch.count` | COUNT | count | — | 1 |

### Hitting

| Key | Aggregation | Unit | Record | Min n |
|---|---|---|---|---|
| `hit.max_exit_velocity` | MAX `exit_velocity_mph` | mph | ↑ | 3 |
| `hit.avg_exit_velocity` | AVG `exit_velocity_mph` | mph | ↑ | 5 |
| `hit.max_distance` | MAX `distance_ft` | ft | ↑ | 3 |
| `hit.tracked_batted_balls` | COUNT | count | — | 1 |

### Two choices worth defending

**Spin rate produces no record.** Whether higher spin is better depends on the
pitch shape a coach wants. Asserting a direction the facility has not agreed to
would put a number on a leaderboard that nobody asked for. It is tracked and
charted; it just is not an achievement.

**Pitch count produces no record.** Throwing more pitches than ever before is
volume, not performance — and turning it into a PR would reward exactly the
wrong behaviour in a facility working with minors.

**Strike percentage excludes balls in play.** A ball put in play is neither a
strike nor a ball for this purpose. Counting it as a miss would understate every
pitcher who induces contact.

## Personal records

A PR rule is **not** a separate configurable object. It is a metric definition
plus a direction. Splitting them would let the two drift, and a rule whose filters
disagreed with its metric's filters would compare values that were never
comparable.

```
RecordRule(direction=definition.record_direction,
           min_sample_size=definition.min_sample_size)
```

The engine is a pure function over the player's full observation series — see
[ARCHITECTURE.md](ARCHITECTURE.md#the-pr-engine-is-derived-not-incremental) for
why that matters. Behaviour:

- First qualifying observation sets the record; `previous_value` and `delta` are
  `NULL`, because "+86.6" for a first record is nonsense.
- A strictly better value breaks it. **Equalling a record does not.**
- `delta` preserves sign; an improvement on a lower-is-better metric is negative.
- Observations below `min_sample_size` are charted but cannot set a record.
- Ordering is by session date, then start time, then session UUID — deterministic
  regardless of row order, so the progression never depends on query luck.

## Versioning

`calculation_version` is stamped on every observation and record event. If a
formula changes meaning, bump it on the definition; historical values keep the
version that produced them.

Historical statistics are never silently rewritten by a code change. Recalculation
is an explicit, deliberate operation.

## Adding a metric

1. Add a `MetricSeed` to `domain/metric_catalog.py` (or insert the row directly
   for a one-off).
2. Choose `record_direction` honestly — `NONE` unless the facility has actually
   agreed which way is better.
3. Set `min_sample_size` so a single mis-tracked event cannot set a record.
4. Add range guards in `spec` for anything physical.
5. Write a test in `tests/unit/test_metrics_engine.py`.

No frontend change is required. The dashboard reads `/api/v1/metrics` and renders
whatever is configured.
