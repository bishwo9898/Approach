# Going Live

Everything in the repository runs on synthetic data today. This is the path from
that to real athletes, in the order the steps actually unblock each other.

Nothing here is optional-but-nice. Each phase is blocked by the one above it.

---

## Phase A — Get a real TrackMan export (blocks everything)

**This is the single highest-value thing to do, and it is not an engineering
task.** One authorized export answers four open questions at once and unblocks
all real-data work.

Ask your TrackMan contact for:

1. **One real CSV export** from this facility — a single session is enough.
   A day is better. It can be an old one.
2. **Which delivery methods are enabled** on the organization's account:
   Data API, organization FTP export, webhook feed, or manual export only.
3. **Whether the per-pitch identifier is stable** when a session is republished
   as verified. If it is not, event matching needs a different key.
4. **How verified data is signalled** — a column, a separate file, a different
   directory, or an API field.

Send the export to whoever is doing the engineering. Mapping it is roughly a
half-day: add a `ColumnMap` in
`apps/api/src/bsa/integrations/trackman/mapping.py`, register it, and reprocess.
Nothing else in the system changes — that isolation is why the mapping layer
exists.

> **Do not** put a real export into `samples/`. That directory is committed and
> must stay synthetic. Keep real exports outside the repository.

**Until this arrives**, everything below Phase B is blocked, and the system can
only run on synthetic data.

---

## Phase B — Decisions only the facility can make

These need a coach, not a developer, and can happen in parallel with Phase A.

- [ ] **Confirm the metric set.** The eleven starter metrics are a scaffold, not a
      recommendation. See `docs/METRICS.md`. Changing them is a data change.
- [ ] **Confirm minimum sample sizes.** Currently 3 tracked fastballs for a max,
      5 for an average, 10 pitches for a rate. Is a 3-pitch sample enough to
      stand as a record an athlete is measured against?
- [ ] **Decide spin rate.** It is tracked but produces no personal record,
      because whether higher is better depends on the pitch shape you want.
      Say which, or leave it as is.
- [ ] **Confirm the Futures field labels.** "Fastball Velocity", "Exit Velocity",
      "Max Distance" came from how the workflow was described, not from any API.
- [ ] **Confirm session types.** `Bullpen` / `Cage` are invented. What do you
      actually run, and does it appear in the TrackMan export?

---

## Phase C — Before any real athlete data is loaded

This system will hold performance data about minors. None of this is negotiable.

- [ ] **Replace development auth with Clerk.** Create a Clerk application, set
      `BSA_CLERK_JWKS_URL` and `BSA_CLERK_ISSUER`. The API refuses to start in
      production with `BSA_AUTH_PROVIDER=dev`, so this cannot be forgotten.
- [ ] **Decide who gets `ADMIN`.** Admins can remap athlete identities — the
      highest-consequence action in the system. Keep the list short.
- [ ] **Agree a retention policy** for raw imports and athlete data, and confirm
      the facility's consent position for minors. Then implement deletion on
      request; there is no retention policy today.
- [ ] **Move every secret to Google Secret Manager.** Nothing in `.env` in
      production.
- [ ] **Test the authorization boundary with a real player account** once Clerk
      is live. The automated tests cover it, but do it by hand once too.

---

## Phase D — Deploy

Only after Phase C. `docs/ARCHITECTURE.md` has the target topology.

- [ ] Create the GCP project; enable Cloud Run, Cloud SQL, GCS, Secret Manager.
- [ ] Cloud SQL PostgreSQL 16, **automated backups on**, and restore one once to
      prove it works.
- [ ] GCS bucket for raw imports; set `BSA_OBJECT_STORE_BACKEND=gcs` and
      `BSA_GCS_BUCKET`. The API refuses to start in production with a local
      object store, because Cloud Run disks are ephemeral and the archive would
      be silently lost.
- [ ] Deploy the API image (`apps/api/Dockerfile`) to Cloud Run. It runs
      `alembic upgrade head` on start.
- [ ] Deploy the web image (`apps/web/Dockerfile`), building with
      `NEXT_PUBLIC_API_BASE_URL` set to the deployed API URL.
- [ ] Set `BSA_CORS_ORIGINS` to the deployed web origin.
- [ ] Add Sentry or equivalent error tracking.
- [ ] Service accounts at least privilege — the API needs Cloud SQL Client,
      the bucket, and its own secrets. Nothing else.

---

## Phase E — Automate ingestion

Needs Phase A question 2 answered.

- [ ] Implement `TrackmanFtpProvider.discover_sessions` / `fetch_payload`, or the
      API provider. Both already have their place in the code.
- [ ] Cloud Scheduler → Cloud Run Job running `bsa.scripts.ingest`. It is the
      same `IngestionService` the API uses, so there is one ingestion path.
- [ ] Pick a cadence. Overnight is usually right; ingestion is idempotent, so a
      re-run is harmless.
- [ ] Alert on `failed_imports_7d > 0` and on a stale last-successful-import.
      Both are already exposed at `/api/v1/integrations/status`.

---

## Phase F — Futures

Blocked on a question only Futures can answer.

- [ ] **Ask whether a supported integration method exists** for a facility of
      this size: public API, partner API, CSV import, or bulk upload.
- [ ] If yes: auth model, the stable athlete identifier, exact field names and
      units, whether a metric is point-in-time or a dated history, and whether
      there is a sandbox.
- [ ] If no: the manual worklist on the Data Health page stays the product. It
      already removes the hard half of the job — working out *which* numbers
      changed.

We will not reverse engineer, scrape, or script a browser against Futures. See
`docs/FUTURES_INTEGRATION.md` for why.

---

## Day-to-day once live

| Task | Where |
|---|---|
| Import an export by hand | Data Health → Import a TrackMan Export |
| An athlete's data is missing | Data Health → Athlete Mapping Required. Map them; their held sessions are recovered automatically. |
| Check an import actually worked | Data Health → Import History. Rejected rows are kept and shown. |
| Enter records into Futures | Data Health → Futures Updates Pending |
| Re-derive after a metric change | Data Health → Reprocess, on the affected imports |

The Data Health page is the one to check when something looks wrong. A coach who
does not know an import failed will read a stale dashboard as if it were current.
