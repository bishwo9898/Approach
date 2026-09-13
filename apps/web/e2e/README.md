# End-to-end tests

These drive the real application against a real backend. Before running:

```bash
# 1. database + seeded synthetic data
cd apps/api
.venv/bin/alembic upgrade head
.venv/bin/python -m bsa.scripts.seed --reset

# 2. API
.venv/bin/uvicorn bsa.api.app:app --port 8000

# 3. web
pnpm --filter @bsa/web dev

# 4. tests
pnpm --filter @bsa/web e2e
```

They are deliberately excluded from `pnpm test` and from the default CI job,
which would otherwise need a database and two long-running servers to run a unit
test suite.
