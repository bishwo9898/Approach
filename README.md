# Baseball Player Analytics Platform

Internal player analytics for a baseball training facility. Ingests TrackMan
performance data, maintains our own historical database, calculates metrics and
personal records, and gives coaches and athletes dashboards over it.

**This application is the analytical source of truth.** TrackMan is a data
source; The Futures App is a destination. Both sit behind adapters.

> No real athlete data is **in this repository**. Real exports live in
> `CSV files/` and `imports/`, both gitignored; every fixture and test uses
> invented athletes. No vendor credentials are present anywhere.

## Status

Running on one real athlete's live at-bat session — 66 pitches faced, 16 batted
balls measured. The athlete is loaded from their export; their name is not in
this repository.

| | |
|---|---|
| Live at-bat ingestion | **Working on real TrackMan exports** |
| Hitting session report | Contact quality, swing decisions, insights, video |
| Roles | Coach and Player. A player reaches only their own data. |
| TrackMan session CSV | Working, idempotent, against a **synthetic** schema |
| Metrics engine | Configurable definitions, 11 starter metrics |
| PR engine | Derived progression, handles verified corrections |
| Preliminary → verified reconciliation | Working |
| Coach view | Athlete list, session report, data health |
| Player view | Their own session report, server-enforced |
| Identity resolution | Map an unknown athlete; their held data is recovered automatically |
| Futures sync | Backend only — no data behind it yet, so nothing is on screen |
| Auth | Fixed development accounts; Clerk interface ready, refused in production |
| Tests | 151 backend, 29 frontend, 5 end-to-end |

## Quick start

**One command.** Everything runs in Docker — no Python, Node or database setup.

```bash
docker compose up -d --build
```

```bash
docker compose exec api python -m bsa.scripts.seed --reset
```

Open **http://localhost:3000** and sign in. The seed prints the passcodes;
in development they are `coach` and `player`.

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
<summary>Running natively instead — also one command</summary>

Prerequisites: Python 3.12+, Node 20+, [`uv`](https://docs.astral.sh/uv/), `pnpm`.

```bash
docker compose down        # stop the containers first -- see the note above
docker compose up -d db    # just PostgreSQL, on :5433
./scripts/dev-setup.sh     # installs, migrates and seeds; safe to re-run
```

Then start the two servers in separate terminals:

```bash
cd apps/api && .venv/bin/uvicorn bsa.api.app:app --reload --port 8000
```

```bash
pnpm --filter @bsa/web dev
```

API docs: http://localhost:8000/docs

</details>

<details>
<summary>If `docker compose build` hangs</summary>

A build that stalls at `load metadata for docker.io/...` while `curl
https://registry-1.docker.io/v2/` works from your shell is Docker Desktop's
builder, not this repository. Restart Docker Desktop and build again. If you
need to keep working in the meantime, use the native setup above.

</details>

## Loading a real TrackMan export

```bash
# 1. See what the file contains. Reads only; writes nothing.
cd apps/api
.venv/bin/python -m bsa.scripts.inspect_csv "../../CSV files/<athlete>/<export>.csv"
```

If it reports a matching schema, import it from **Data Health → Import a
TrackMan export**. If it does not, add a `ColumnMap` in
`apps/api/src/bsa/integrations/trackman/mapping.py` using the column names it
printed — nothing outside that file changes.

Athletes the export names but we do not recognize are **held, never guessed at**.
They appear under *Athlete mapping required*, where you map them to an existing
athlete or create one on the spot; their held sessions are then reprocessed and
attributed automatically.

> Real exports live in `CSV files/` and `imports/`, both gitignored. They contain
> real athlete data and must never be committed. `samples/trackman/` holds the
> synthetic fixtures that do belong in the repository.

### Loading an athlete

```bash
cd apps/api
.venv/bin/python -m bsa.scripts.seed_athlete "../../CSV files/<athlete>/<export>.csv"
```

This reads the athlete from the export, registers their TrackMan identity, and
ingests the session. Then sign in at http://localhost:3000 as **Coach** or
**Player** — the player account is linked to whichever athlete you loaded.

Re-run it with the next athlete's export as more data arrives; no code changes.

## What the app shows today

Only what the data supports. A live at-bat export measures four things
reliably — the pitch, whether the batter swung, whether they hit it, and how
hard and at what angle — so the athlete's page is built from exactly those:

| | |
|---|---|
| Hardest ball / typical ball | best and average exit velocity, with the count behind them |
| Line-drive window | share of batted balls between 8° and 32° |
| Swings that missed | whiff rate, with the number of swings |
| What this session says | strengths and things to work on, each guarded by a sample size |
| Every ball put in play | exit velocity against launch angle, plus the full list |
| How you handled each pitch | fastball vs breaking, grouped by measured movement |
| Video | clips a coach attaches, tied to the pitch they show |

Nothing else is on screen. Metrics, personal records and multi-session trends
exist in the backend and are tested, but they need more than one session before
they mean anything, so they are not displayed yet.

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
| [DEPLOY.md](docs/DEPLOY.md) | Putting a shareable demo on Vercel + Render |
| [GOING_LIVE.md](docs/GOING_LIVE.md) | **Start here** — the path from synthetic data to real athletes |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layering, idempotency, reconciliation, why the PR engine is derived |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | All 17 tables, constraints, and what they answer |
| [METRICS.md](docs/METRICS.md) | Metric configuration, the starter set, PR rules |
| [TRACKMAN_INTEGRATION.md](docs/TRACKMAN_INTEGRATION.md) | Synthetic schema, parsing rules, **open questions** |
| [FUTURES_INTEGRATION.md](docs/FUTURES_INTEGRATION.md) | Why there is no automation, **open questions** |
| [SECURITY.md](docs/SECURITY.md) | Threat model, authorization, secrets, minors |
| [DECISIONS.md](docs/DECISIONS.md) | Every significant choice, with its rationale and assumptions |
