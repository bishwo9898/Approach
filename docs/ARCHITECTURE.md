# Architecture

## The one idea everything else follows from

**This application is the analytical source of truth.** TrackMan is a data
source; The Futures App is a destination. Neither is our database, and neither
appears in our business logic.

```
TrackMan (CSV today; FTP / Data API / feed later)
        │
        ▼
 TrackMan adapter ──────► raw payload archived to object storage (never discarded)
        │
        ▼
 normalization + validation      canonical units, our vocabulary, row-level issues
        │
        ▼
    PostgreSQL                   sessions, pitch_events, hit_events
        │
        ▼
  Metrics engine                 configurable definitions -> metric_observations
        │
        ▼
     PR engine                   observation series -> personal_record_events
        │
        ▼
   Analytics API                 FastAPI, versioned, organization-scoped
        │
        ├────────► Coach dashboard
        ├────────► Player dashboard
        └────────► Futures synchronization queue (manual today)
```

If TrackMan changes its export format or Futures finally exposes an API, exactly
one adapter changes. Nothing in `domain/` or `services/` knows either vendor
exists beyond the string `"trackman"` used as a provider key.

## Layering

Dependencies point downward only. This is enforced by review, not tooling, so it
is stated plainly:

| Layer | Package | May import |
|---|---|---|
| API | `bsa.api` | services, domain, db, core |
| Application services | `bsa.services` | domain, db, integrations, core |
| Domain | `bsa.domain` | core **only** |
| Persistence | `bsa.db` | domain, core |
| Integrations | `bsa.integrations` | domain, core |
| Core | `bsa.core` | nothing |

`bsa.domain` contains no I/O of any kind — no session, no HTTP, no filesystem.
That is what lets the metric engine and the PR engine, the two places a silent
bug would be most expensive, be tested exhaustively without a database.

Route handlers contain no SQL. Queries live in `bsa/db/repositories/`, which are
plain functions taking a `Session` rather than classes, because the repositories
exist to centralize queries — not to abstract the database away. We use
PostgreSQL deliberately (JSONB, `ON CONFLICT`, GIN indexes) and swapping it out
is not a goal worth paying for.

## Why a modular monolith

One FastAPI application, one database, one deployment. The facility has one
organization, a handful of coaches, and a few thousand events per training day.
Microservices, Kafka, Redis and Celery would each add an operational failure mode
without removing one. The module boundaries above are real; the process boundary
is not, and does not need to be yet.

Scheduled ingestion runs as a **Cloud Run Job** executing the same
`IngestionService` the API uses, so there is one ingestion code path, not two.

## Idempotency: the central engineering constraint

Ingestion will be re-run. Files will be re-uploaded. TrackMan will republish
sessions. Every one of those must be safe:

| Concern | Mechanism |
|---|---|
| Same bytes ingested twice | SHA-256 checksum, unique per `(organization, provider)` |
| Same session in a different file | Unique `(organization, provider, external_session_id)`; upsert |
| Same event re-parsed | Unique `(session_id, external_event_id)`; `ON CONFLICT DO UPDATE` |
| Metric recalculated | Unique observation key; upsert, then delete what is no longer produced |
| Record re-detected | Unique `(player, metric, session)` on `personal_record_events` |
| Futures value re-queued | Unique `(player, metric, destination, pr_event)`; completed jobs never reopen |

## The PR engine is derived, not incremental

The single most consequential design decision in the system.

`compute_progression(rule, observations)` is a **pure function** from a player's
complete observation series to the full list of moments their record was broken.
It is not "compare the new value against the stored PR".

That buys three properties the incremental version cannot have:

1. **Idempotency.** Recomputing from the same observations is byte-identical, so
   re-importing a session never announces an achievement twice.
2. **Correct reconciliation.** When TrackMan republishes a session as verified
   with a lower velocity, the record that session claimed simply does not appear
   in the recomputed progression, and the previous record is restored —
   automatically, with no special-case code.
3. **Testability.** The hardest logic in the product has no database in it.

The cost is recomputing a player's series on each ingest. At facility scale
(hundreds of sessions per athlete per year) that is microseconds, and it is the
right trade for correctness. If a facility ever reaches a scale where it is not,
the fix is to bound the recomputation window — not to make the engine stateful.

## Preliminary vs verified reconciliation

TrackMan may publish a session as preliminary and later republish it corrected.

```
preliminary session ingested → dashboard updated, values labelled "Preliminary"
        │
verified republish arrives (same external_session_id)
        │
        ├─ session row UPDATED in place (never duplicated), status → VERIFIED
        ├─ events upserted on (session, external_event_id)
        ├─ events the republish omits are deleted — but only if the file parsed
        │  cleanly and every athlete resolved (see below)
        ├─ metric observations recalculated and overwritten
        └─ PR progression recomputed; records the new data no longer supports are
           marked superseded (not deleted — the audit trail must show what the
           coach was told at the time)
```

A verified session is **never** downgraded back to preliminary by a late
preliminary file.

**Pruning requires an authoritative payload.** Events absent from an incoming
file are deleted only when every row parsed and every athlete resolved. If rows
were rejected or an athlete was unmapped, an event is missing because *we*
failed to read it, not because the source removed it — and deleting real
measurements on that basis is the worst kind of bug, because the dashboard
renders happily afterwards. An imperfect import only ever adds and updates.

## Reprocessing: what the raw archive is for

Source bytes are archived before they are interpreted, and
`IngestionService.reprocess` replays a stored import through the ordinary
pipeline. Two things depend on it:

- **Recovering held data.** When an unknown athlete is mapped, the imports whose
  events were held for them are found (via their `PLAYER_UNRESOLVED` import
  issues) and re-run. Without this, mapping an athlete would fix nothing that had
  already happened, and the resolution queue would be a dead end.
- **Re-deriving history** after a parser or metric change, without asking the
  facility to re-export from TrackMan.

Reprocessing goes through the same path as a first ingest, so it inherits every
idempotency guarantee: replaying an import that needs nothing changes nothing.
Both uses are audited as `IMPORT_REPROCESSED`.

## Identity: never guess

An athlete is resolved **only** by an explicit `(provider, external_id)` row in
`external_player_identities`. Name matching resolves nothing and maps nothing.

An unknown TrackMan id goes to `identity_resolution_items` and its events are
held, not attached. Attributing one athlete's data to another is the single worst
failure this system can produce: it is invisible, it corrupts two athletes'
histories at once, and nobody would think to look for it.

Mapping is an ADMIN action, is audited, and triggers the reprocessing described
above so the athlete's held sessions are actually recovered.

## Metrics are data, not code

"Fastball max velocity" is a row in `metric_definitions`, not a function. A
definition carries its event source, aggregation, canonical unit, record
direction, minimum sample size and a small structured `spec` describing which
events feed it.

The `spec` vocabulary is deliberately tiny — field, filters, numerator filters,
range guards — and is not a query language. It can express what a coach-editable
metric needs and little else. Anything requiring real expressiveness should
become a new named aggregation with a test, not a more powerful DSL nobody can
reason about.

Frontend components never name a metric key. The dashboard reads the catalog
from `/api/v1/metrics` and renders whatever the facility has configured.

## Units

Canonical units are declared once in `bsa/core/units.py`: mph, rpm, inches,
degrees, feet, count, percent, seconds.

Conversion happens in exactly one place — the vendor adapter — and every value
passes through `convert()` even when the factor is 1.0, so the conversion path is
always exercised and a future unit change is a one-line edit. An unsupported
conversion raises rather than guessing; a silently wrong factor produces
plausible numbers nobody catches.

`MetricDefinition.unit` is `NOT NULL`, and event columns carry their unit in the
column name (`velocity_mph`, `distance_ft`). A stored measurement without a
known unit is a bug.

## Authorization

Authentication is delegated to a provider (Clerk is the intended first one).
Authorization is ours and lives in our database.

```
credential ──► AuthProvider.verify() ──► subject id
                                            │
                          users(auth_provider, auth_subject)  ← our row
                                            │
                          organization_id + role + player_id
```

Nothing a token claims about roles or organizations is read. Every repository
function takes `organization_id` and filters on it, so cross-tenant access is
impossible at the data layer regardless of what the API checked. `authorize_player`
is the single choke point for athlete access; a `PLAYER` may read only the athlete
their own user row points at, and gets a 404 — not a 403 — for a foreign athlete,
because the difference would confirm who is enrolled at the facility.

The frontend's `AuthGate` is navigation, not a control. Deleting it would make the
app confusing, not insecure.

## Time

"What did Jake do today?" means today *at the facility*. A 7pm session in New
York is already tomorrow in UTC, so a UTC-based "today" shows the coach an empty
dashboard every evening — exactly when they are most likely to look. Every
calendar-date default resolves through `bsa/core/clock.py` using
`Organization.timezone`.

## Multi-tenancy

There is one organization today. Every tenant-owned table still carries
`organization_id`, because retrofitting multi-tenancy onto a live analytics
database costs vastly more than carrying one column from the start.

## Deployment target

```
                 INTERNET
                    │
                    ▼
             Next.js (Cloud Run)
                    │
                    ▼
             FastAPI (Cloud Run)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    Cloud SQL      GCS     Secret Manager
    PostgreSQL   (raw imports)

TrackMan FTP/API ──► Cloud Scheduler ──► Cloud Run Job ──► IngestionService
```

Not configured yet, by design: the local MVP works first. Environment-specific
configuration is already clean (`bsa/core/config.py` refuses to boot in
production with development auth or a local object store).
