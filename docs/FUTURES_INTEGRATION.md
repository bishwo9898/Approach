# The Futures App Integration

## Status: not integrated, and deliberately so

We do not know how The Futures App accepts data. **Unconfirmed:** API access,
partner API access, CSV import, bulk ingestion, webhooks.

### What we will not do

Regardless of convenience or pressure, this project will not:

- reverse engineer Futures' private endpoints,
- drive its UI with a scripted browser,
- scrape it.

Those approaches break without warning, are very likely to violate its terms of
use, and put the facility's own account at risk. They would also be the kind of
thing that works in a demo and fails in production on a Tuesday morning with no
error anyone can act on.

So: the interface exists, two honest implementations sit behind it, and the real
one gets written when a supported method is confirmed.

## The interface

```python
class FuturesProvider(Protocol):
    name: str
    def get_player_mapping(self, external_player_id: str) -> dict[str, str] | None: ...
    def update_player_metric(self, push: MetricPush) -> PushResult: ...
```

| Implementation | Purpose |
|---|---|
| `ManualFuturesProvider` | **Default.** Declines every push as `requires_manual_entry`, which turns it into a coach worklist item. This is the honest outcome today, not a failure. |
| `MockFuturesProvider` | Records what would have been sent, so the sync pipeline is exercised end to end in tests without inventing a vendor API. Refused outside development. |

## Why this is useful before any automation exists

The coach's actual pain is not typing numbers. It is working out **which** numbers
changed since last time.

Every new personal record on a mapped metric queues a `sync_job` carrying the
athlete, the destination field label, and the exact value in the destination's
unit. The coach dashboard renders:

```
Futures Updates Pending

Ryan Jones      Fastball Velocity     87.8 mph    [Mark updated]
Marc Cole       Exit Velocity         92.9 mph    [Mark updated]
Jake Williams   Max Distance          363 ft      [Mark updated]
```

That removes the hard half of the job with zero integration, and "Mark updated"
is audited — it is the only evidence we will ever have that the external system
actually matches ours.

## Data model

**`external_metric_mappings`** — our metric → their field, with the destination's
unit and precision. Seeded with three mappings the facility is believed to
maintain by hand:

| Our metric | Futures field | Unit |
|---|---|---|
| `pitch.fastball.max_velocity` | Fastball Velocity | mph |
| `hit.max_exit_velocity` | Exit Velocity | mph |
| `hit.max_distance` | Max Distance | ft |

These field labels come from how the facility described their workflow. They are
**not** read from any Futures API, and should be confirmed before anyone relies
on them.

**`sync_jobs`** — one pending or completed push, keyed on the PR event that
triggered it so re-running ingestion never duplicates a worklist item. Value and
unit are frozen at queue time. A `SYNCED` job is never reopened by a
recalculation: the coach already typed that value and must not be sent back.

## Unit conversion

If a destination expects a different unit, conversion happens once, at push time,
through `bsa.core.units`. An unsupported conversion **fails the push and logs**
rather than sending the raw number — queueing `88` labelled `km/h` would be far
worse than queueing nothing.

## Open questions for Futures

Blocking Phase 6:

1. **Does a supported integration method exist at all** for a facility of this
   size — public API, partner API, CSV import, or bulk upload?
2. **If an API exists:** auth model, base URL, rate limits, and whether it is
   covered by an agreement the facility already has.
3. **What identifies an athlete in Futures?** We need a stable external id to
   store in `external_player_identities` under `provider = "futures"`. Name
   matching is not acceptable here either.
4. **What are the exact field names and units** for the values the coach
   currently enters by hand?
5. **Is a metric value a point-in-time record or a dated history?** This decides
   whether we push only new records, or a full series.
6. **Is there a sandbox** to test against before writing to live athlete records?
7. **What is the expected update cadence** — on every PR, nightly, or on demand?

Until (1) is answered, the manual worklist is the product.
