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
| Tests | 109 backend, 22 frontend, 7 end-to-end |

## Quick start

### Everything in Docker (nothing else to install)

```bash
cp .env.example .env
docker compose up -d --build          # db + api + web
docker compose exec api python -m bsa.scripts.seed --reset
```

Then open http://localhost:3000 and sign in as **Chris Coach**.
The seed prints the development sign-in tokens.

### Or run the apps natively (for development)

Prerequisites: Docker, Python 3.12+, Node 20+, [`uv`](https://docs.astral.sh/uv/),
`pnpm`.

```bash
cp .env.example .env
docker compose up -d db               # just PostgreSQL, on :5433
```

#### API

```bash
cd apps/api
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/python -m bsa.scripts.seed --reset
.venv/bin/uvicorn bsa.api.app:app --reload --port 8000
```

API docs: http://localhost:8000/docs

#### Web

```bash
pnpm install
pnpm --filter @bsa/web dev    # http://localhost:3000
```

Sign in with one of the seeded accounts (`Chris Coach` for the coach dashboard,
`Jake Williams` for the player view).

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
