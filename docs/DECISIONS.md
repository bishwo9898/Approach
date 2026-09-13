# Decisions

Every entry records what was decided, why, and what would change it. Assumptions
are marked **ASSUMPTION** and should be challenged.

---

## 1. The PR engine derives the whole progression instead of comparing to a stored record

**Decision.** `compute_progression` is a pure function from a player's complete
observation series to every moment their record was broken. It is not "compare
the new value to the stored PR and maybe write a row".

**Why.** Idempotency, reconciliation and testability all fall out of it for free.
Re-importing a session produces a byte-identical progression, so no achievement is
announced twice. A verified republish that lowers a value simply does not produce
that record, and the earlier one is restored — with no special-case code. And the
hardest logic in the product has no database in it.

**Cost.** Recomputing a player's series on each ingest. At facility scale that is
microseconds.

**Would change if.** A facility reaches a scale where recomputation is measurably
expensive. The fix then is to bound the recomputation window, **not** to make the
engine stateful.

---

## 2. Pruning requires an authoritative payload

**Decision.** Events absent from an incoming file are deleted only when every row
parsed and every athlete resolved.

**Why.** This was found by using the app. A malformed test file containing 6 of
30 rows was treated as authoritative and deleted 24 real pitch events; the
dashboard then rendered happily with `n=3`. If rows were rejected or an athlete
was unmapped, an event is missing because *we* failed to read it — not because
the source removed it. An imperfect import must only add and update.

**Would change if.** TrackMan gains an explicit "this file is a partial update"
signal, which would let us be precise instead of conservative.

---

## 3. A PR rule is a metric definition plus a direction, not a separate table

**Decision.** No `personal_record_rules` table. `record_direction` and
`min_sample_size` live on `MetricDefinition`.

**Why.** The brief describes a configurable rule with metric, aggregation,
filters, context, minimum sample and active flag — every one of which already
exists on the metric definition. A separate table would let the two drift, and a
rule whose filters disagreed with its metric's filters would compare values that
were never comparable.

**Would change if.** A single metric genuinely needs several record rules (e.g.
records tracked per drill as well as overall). The natural answer then is still
not a rules table — it is another metric definition with different filters.

---

## 4. Metrics are configuration rows with a deliberately weak selector language

**Decision.** `MetricDefinition.spec` is a small closed vocabulary — field,
filters, numerator filters, range guards — validated by Pydantic.

**Why.** Coaches will change the metric set repeatedly; hardcoding each
calculation makes every change a deployment. But a general expression language
would be a second, untested query engine that nobody can reason about or debug at
6am. The vocabulary covers what a coach-editable metric needs and stops there.

**Would change if.** A metric arrives that genuinely cannot be expressed. The
answer is a new named aggregation with a test — not a more powerful DSL.

---

## 5. Metrics with no agreed direction produce no records

**Decision.** `pitch.fastball.avg_spin_rate` and the volume counts have
`record_direction = NONE`.

**Why.** Whether higher spin is better depends on the pitch shape a coach wants.
Asserting a direction the facility has not agreed to puts a number on a
leaderboard nobody asked for. And a "pitch count PR" would reward throwing more
than ever before — exactly the wrong incentive in a facility working with minors.

**ASSUMPTION.** The coach has not yet told us which direction they want for spin.
Ask them; this is a one-row change.

---

## 6. Session-scope observations only; rollups are derived

**Decision.** Only `period = SESSION` observations are materialized. Day, week,
month and all-time windows are computed on read.

**Why.** Session values are the atoms. Materializing rollups means five more
things to invalidate every time a session is corrected, and the correction path is
already the subtlest part of the system. Reading a 30-day window is an indexed
scan over a handful of rows.

**Would change if.** Cross-roster queries over years become slow. The model
already supports materializing other periods — `period` and `period_start` exist
on the table for exactly that.

---

## 7. Synchronous SQLAlchemy, not async

**Decision.** Sync engine, sync sessions, sync FastAPI endpoints.

**Why.** The workload is ingestion batches and dashboard reads, both short and
Postgres-bound. Async would buy nothing here and costs a materially harder
debugging story. FastAPI runs sync endpoints in a threadpool, which is the right
trade at this scale.

**Would change if.** The API becomes I/O-bound on external calls, which would
mean a real TrackMan API integration in the request path — something we would
avoid anyway.

---

## 8. Enums stored as `VARCHAR` + `CHECK`, not native Postgres `ENUM`

**Decision.** `native_enum=False` on every enum column.

**Why.** Adding a value to a native enum requires `ALTER TYPE`, which is awkward
to run transactionally and awkward to reverse. Vendor vocabularies will grow. A
checked varchar gives the same integrity with ordinary migrations.

---

## 9. Integrations live inside the API package, not in a top-level `integrations/`

**Decision.** Vendor adapters are at `apps/api/src/bsa/integrations/` rather than
a sibling top-level directory.

**Why.** The brief proposed a top-level `integrations/`, and invited a stronger
organization. A separate top-level Python directory would need to be its own
installable package with its own dependency set, adding real friction for a
boundary that is enforced by the adapter Protocols, not by directory depth. The
separation the brief actually asks for — business logic that does not depend on
vendors — is achieved and testable as it stands.

**Would change if.** A second application (e.g. a standalone ingestion worker)
needs the adapters without the API. `uv` workspaces make that a mechanical move.

---

## 10. Deviation: seed data flows through the real ingestion pipeline

**Decision.** `bsa.scripts.seed` generates synthetic TrackMan CSVs and ingests
them through the same `IngestionService` production uses, rather than inserting
metrics and records directly.

**Why.** Directly-inserted seed data produces a dashboard that looks right while
proving nothing. This way, a broken parser, metric or PR engine shows up the
moment you seed.

---

## 11. `synthetic.v1` is our schema, and is labelled as such everywhere

**Decision.** The CSV columns the parser understands were invented by us, modelled
on the expected *shape* of a TrackMan event export.

**Why.** We were told not to invent TrackMan column names. Inventing a mapping
that looked authoritative would be worse than an obviously synthetic one, because
someone would eventually trust it. The mapping layer is isolated so the real
schema is an additive change.

**ASSUMPTION.** A TrackMan event export is one row per pitch, with batted-ball
columns populated when the ball is put in play. This matches the general shape of
pitch-tracking exports but is **unverified**. If it is wrong, `ParseResult` is
the seam that absorbs it.

---

## 12. No Futures automation of any kind

**Decision.** `ManualFuturesProvider` (worklist) and `MockFuturesProvider`
(tests). Nothing else.

**Why.** No supported ingestion method is confirmed. Reverse engineering,
scripted browser automation and scraping were all rejected: they break silently,
likely violate terms of use, and risk the facility's account.

**Still useful.** The queue removes the hard half of the coach's job — working out
*which* numbers changed — with zero integration.

---

## 13. Dev auth provider, with a hard production guard

**Decision.** Phase 1 authenticates with static seeded tokens. `Settings` refuses
to boot with `BSA_AUTH_PROVIDER=dev` when `BSA_ENV=production`.

**Why.** Clerk requires an application we do not have. Stubbing auth entirely
would have left the authorization model untested, which is the part that actually
matters. The dev provider lets the full role and athlete-scope model be exercised
by real integration tests today, and it physically cannot reach production.

**ASSUMPTION.** Clerk is acceptable. The `AuthProvider` Protocol makes any
JWT/JWKS provider a drop-in.

---

## 14. Roles come from our database, never from a token claim

**Decision.** `AuthProvider.verify()` returns only a subject id. Role,
organization and athlete link are read from `users`.

**Why.** An external provider must not be able to grant itself access to a
minor's data through a claim in a token.

---

## 15. A foreign athlete returns 404, not 403

**Decision.** Cross-organization access reports "not found".

**Why.** Distinguishing "exists but not yours" from "does not exist" confirms
which athletes are enrolled at the facility. Within an organization, a player
reaching another athlete gets 403 — the roster is not secret from staff, and the
clearer error is worth more there.

---

## 16. Facility-local dates, not UTC

**Decision.** Every calendar-date default resolves through `Organization.timezone`.

**Why.** Found by using the app: at 22:45 New York time the dashboard showed
zero sessions, because UTC had already rolled over to the next day. A 7pm session
is exactly when a coach is most likely to be looking.

---

## 17. shadcn/ui idiom, hand-written components

**Decision.** Tailwind + `class-variance-authority` + `tailwind-merge`, with the
handful of primitives written by hand rather than pulled in via the shadcn CLI.

**Why.** shadcn components are meant to be copied into the repo and owned. Phase
1 needs six primitives; writing them directly avoids a CLI dependency and an
interactive init step in CI, and the result is source-compatible with adding more
via the CLI later.

---

## 18. Frontend types are generated from the API's own OpenAPI document

**Decision.** `apps/web/src/lib/api-types.ts` is generated by `openapi-typescript`
from `packages/shared/openapi.json`, which the backend writes itself.
`types.ts` contains aliases only. CI regenerates both and fails on a diff.

**Why.** This was hand-maintained in the first pass and flagged as owed. Hand
mirroring two type systems works right up until someone renames a field, at which
point the frontend compiles happily against a shape the server no longer sends.

**Consequence worth knowing.** It pushed a fix back into the API: response
schemas now declare their domain enums instead of `str`, because that is what
makes the generated TypeScript a checked union rather than an open string. The
contract got more honest because a consumer depended on it.

---

## 19. Resolving an athlete reprocesses their held imports

**Decision.** Mapping an unknown athlete re-runs the imports whose events were
held for them, from the archived source bytes, through the ordinary pipeline.

**Why.** Without it the resolution queue is a dead end: an admin maps the athlete,
nothing happens to the data that prompted it, and the sessions stay invisible
forever. Back-filling rows directly would be the obvious shortcut and the wrong
one — recovered data must pass the same validation, metric calculation and PR
logic as a first ingest.

**Safe because** reprocessing is idempotent. Replaying an import that needs
nothing changes nothing, which is asserted by a test.

**Escape hatch.** `reprocess: false` on the resolve call, for an admin correcting
a mapping who does not want an immediate re-run.

---

## 20. The repository root is found by marker, not by counting parents

**Decision.** `bsa.scripts.paths.repo_root()` walks upward looking for
`pnpm-workspace.yaml`.

**Why.** Hand-counting `.parents[n]` shipped a wrong path twice, in two separate
scripts, and the failure was silent — generated files landed in a plausible
directory nobody opens. A marker cannot be broken by moving a module. Covered by
a test.

---

## 21. Tests run against real PostgreSQL

**Decision.** Integration tests use a live database, in a transaction rolled back
per test.

**Why.** The guarantees this system makes — upsert idempotency, uniqueness
constraints, JSONB, `ON CONFLICT` — are database behaviours. A fake would only
prove the fake works.

**Trade.** The suite needs `BSA_TEST_DATABASE_URL`. It skips cleanly with a clear
message when unavailable rather than failing confusingly.

---

## Open assumptions to confirm with the facility

1. **Metric set.** The nine starter metrics are a scaffold, not a
   recommendation. Which does the coach actually want?
2. **Minimum sample sizes.** 3 for a max, 5 for an average, 10 for a rate are
   judgement calls. A coach may consider 3 fastballs too thin for a record.
3. **Spin rate direction.** Currently produces no record. Should it?
4. **Futures field labels.** "Fastball Velocity", "Exit Velocity", "Max Distance"
   come from how the workflow was described. Confirm before relying on them.
5. **Session types.** `Bullpen` / `Cage` are synthetic. What does the facility
   actually run, and does it appear in the TrackMan export?
6. **Retention.** How long is raw import data kept? This holds minors' data and
   currently has no retention policy.
7. **Who gets ADMIN.** It can remap athlete identities — the highest-consequence
   action in the system.
8. **Parent access.** Out of scope for now, but it changes the authorization
   model meaningfully when it lands. Worth designing before building.
