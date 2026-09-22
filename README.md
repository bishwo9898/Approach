# Baseball Player Analytics Platform

Internal player analytics for a baseball training facility. Ingests TrackMan
performance data, maintains our own historical database, calculates metrics and
personal records, and gives coaches and athletes dashboards over it.

**This application is the analytical source of truth.** TrackMan is a data
source; The Futures App is a destination. Both sit behind adapters.

> All data in this repository is **synthetic**. No real athlete data and no
> vendor credentials are present anywhere, including in tests.

## Status — Phase 1 complete

| | |
|---|---|
| TrackMan CSV ingestion | Working, idempotent, against a **synthetic** schema |
| Metrics engine | Configurable definitions, 11 starter metrics |
| PR engine | Derived progression, handles verified corrections |
| Preliminary → verified reconciliation | Working |
| Coach dashboard | Today, PR feed, search, player page, data health |
| Player dashboard | Self-scoped, server-enforced |
| Identity resolution | Map an unknown athlete; their held data is recovered automatically |
| Futures sync | Manual worklist (no supported API confirmed) |
| Auth | Dev provider; Clerk interface ready, refused in production |
| Tests | 112 backend, 28 frontend, 7 end-to-end |

## Quick start

**One command.** Everything runs in Docker — no Python, Node or database setup.

```bash
docker compose up -d --build
```

```bash
docker compose exec api python -m bsa.scripts.seed --reset
```

Open **http://localhost:3000** and sign in as **Chris Coach** (or **Dana Admin**
for import and athlete-mapping tools). The seed prints every login.

To stop: `docker compose down`. To wipe the data too: `docker compose down -v`.

### Checking which stack you are talking to

`http://localhost:8000/health` reports the database it is attached to:

```json
{ "status": "ok", "database": "ok", "database_target": "db:5432/bsa" }
```

`db:5432` is the Docker database. `localhost:5432` is a local one. This matters
because **running Docker and a local API at the same time collides on port 8000**
— your browser may reach one while your terminal reaches the other, each with
different data. Run one or the other, not both.

<details>
<summary>Running natively instead (faster iteration for development)</summary>

Prerequisites: Python 3.12+, Node 20+, [`uv`](https://docs.astral.sh/uv/), `pnpm`.

```bash
docker compose down            # stop the containers first -- see the note above
cp .env.example .env
docker compose up -d db        # just PostgreSQL, on :5433
```

```bash
cd apps/api
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/python -m bsa.scripts.seed --reset
.venv/bin/uvicorn bsa.api.app:app --reload --port 8000
```

```bash
pnpm install && pnpm --filter @bsa/web dev
```

API docs: http://localhost:8000/docs

</details>

## When your real TrackMan data arrives

Three steps, in order.

**1. See what the file contains.** This reads only; it writes nothing.

```bash
# put the file in ./imports first -- that folder is mounted into the container
docker compose exec api python -m bsa.scripts.inspect_csv /data/imports/export.csv
```

It lists every column, flags the ones that look like fields we need, and tells
you whether a known schema matches. If one does, skip to step 3.

**2. Add the real column names.** If no schema matched, add a `ColumnMap` in
`apps/api/src/bsa/integrations/trackman/mapping.py` using the names from step 1,
and register it in `COLUMN_MAPS`. Nothing outside that one file changes.

**3. Import it.** Data Health → *Import a TrackMan export*. Then:

- Athletes we do not recognize appear under **Athlete mapping required**. Map
  each to an existing athlete, or create a new one right there — the form is
  pre-filled from the name TrackMan reported. Their held sessions are
  reprocessed and attributed automatically.
- **Import history** shows any rejected rows and why.
- Metrics, personal records and the dashboards follow on their own.

Re-importing the same file is always safe; it is detected and does nothing.

## Repository layout

```
apps/
  api/                       FastAPI application and ingestion pipeline
    src/bsa/
      core/                  config, units, logging, errors, clock
      domain/                pure business logic -- NO I/O
        metrics_engine.py      events -> one number
        pr_engine.py           observation series -> record progression
        metric_spec.py         the metric selector vocabulary
        metric_catalog.py      starter metric definitions (seed data)
      db/
        models/              17 SQLAlchemy models
        repositories/        queries, organization-scoped
      services/              ingestion, metrics, records, sync, analytics, audit
      integrations/
        trackman/            CSV provider + column mapping + extension points
        futures/             interface, manual worklist, mock
        storage/             object store (local / GCS)
        auth/                dev + Clerk
      api/v1/                versioned routers
      scripts/               seed, ingest, synthetic data, sample generator
    alembic/versions/        migrations
    tests/{unit,integration}
  web/                       Next.js 15, App Router, TanStack Query, ECharts
    src/{app,components,hooks,lib}
samples/trackman/            SYNTHETIC sample exports
docs/                        architecture, data model, metrics, integrations, security, decisions
```

## Commands

### Backend (`apps/api`)

```bash
.venv/bin/pytest                                   # all tests
.venv/bin/pytest -m "not integration"              # no database needed
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/mypy                                     # strict
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "..."
.venv/bin/python -m bsa.scripts.seed --reset --weeks 14
.venv/bin/python -m bsa.scripts.ingest path/to/export.csv
.venv/bin/python -m bsa.scripts.make_samples       # regenerate samples/
.venv/bin/python -m bsa.scripts.dump_openapi       # refresh packages/shared/openapi.json
```

### Frontend (`apps/web`)

```bash
pnpm test          pnpm lint          pnpm typecheck
pnpm build         pnpm format        pnpm e2e
pnpm gen:api       # regenerate src/lib/api-types.ts from the OpenAPI document
```

The frontend's types are **generated** from the backend's OpenAPI document, so
the two cannot drift. After changing an API schema:

```bash
cd apps/api && .venv/bin/python -m bsa.scripts.dump_openapi
pnpm --filter @bsa/web gen:api
```

CI fails if either output is stale.

## Try the pipeline

```bash
cd apps/api
S=../../samples/trackman

.venv/bin/python -m bsa.scripts.ingest $S/session_2026-09-12_preliminary.csv
.venv/bin/python -m bsa.scripts.ingest $S/session_2026-09-12_preliminary.csv   # SKIPPED_DUPLICATE
.venv/bin/python -m bsa.scripts.ingest $S/session_2026-09-12_verified.csv      # updates in place
.venv/bin/python -m bsa.scripts.ingest $S/session_2026-09-12_unknown_player.csv # queued, not guessed
.venv/bin/python -m bsa.scripts.ingest $S/session_2026-09-12_malformed.csv     # PARTIAL, rest survives
.venv/bin/python -m bsa.scripts.ingest $S/unknown_schema.csv                   # FAILED, cleanly
```

## What this does not do, on purpose

No AI coaching advice, injury prediction, ML, pitch classification, parent
portal, mobile app, public leaderboards, notifications, billing, live streaming,
Futures scraping, Redis, Kafka, Kubernetes or microservices.

Extension points exist. A reliable data foundation comes first.

## Documentation

| | |
|---|---|
| [GOING_LIVE.md](docs/GOING_LIVE.md) | **Start here** — the path from synthetic data to real athletes |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layering, idempotency, reconciliation, why the PR engine is derived |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | All 17 tables, constraints, and what they answer |
| [METRICS.md](docs/METRICS.md) | Metric configuration, the starter set, PR rules |
| [TRACKMAN_INTEGRATION.md](docs/TRACKMAN_INTEGRATION.md) | Synthetic schema, parsing rules, **open questions** |
| [FUTURES_INTEGRATION.md](docs/FUTURES_INTEGRATION.md) | Why there is no automation, **open questions** |
| [SECURITY.md](docs/SECURITY.md) | Threat model, authorization, secrets, minors |
| [DECISIONS.md](docs/DECISIONS.md) | Every significant choice, with its rationale and assumptions |
