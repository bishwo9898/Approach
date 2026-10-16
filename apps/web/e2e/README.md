# End-to-end tests

These drive the real application against a real backend. Before running:

```bash
# 1. database + the provisioned roster and two demo logins
cd apps/api
.venv/bin/alembic upgrade head
.venv/bin/python -m bsa.scripts.provision_roster "<roster export>.csv" \
    --emails birth-year --link-existing --demo-accounts

# 2. API
.venv/bin/uvicorn bsa.api.app:app --port 8000

# 3. web
pnpm --filter @bsa/web dev

# 4. tests
pnpm --filter @bsa/web e2e
```

## Credentials

`provision_roster --demo-accounts` prints a coach login and an athlete login.
The coach address is a role (`coach@<domain>`) and is the default here. The
athlete address is a real person's name, so it is **not** committed -- the
athlete-facing tests skip until you supply it:

```bash
E2E_PLAYER_EMAIL="first.last@approach.com" \
E2E_ATHLETE_QUERY="First" \
pnpm --filter @bsa/web e2e
```

| Variable            | Default                 | What it is                                   |
| ------------------- | ----------------------- | -------------------------------------------- |
| `E2E_PASSWORD`      | `SpringTraining26`      | password the demo accounts were created with |
| `E2E_COACH_EMAIL`   | `coach@approach.com`    | the coach login                              |
| `E2E_PLAYER_EMAIL`  | _(none)_                | an athlete login that has imported data      |
| `E2E_ATHLETE_QUERY` | _(none)_                | roster search term reaching that athlete     |
| `E2E_API_BASE_URL`  | `http://localhost:8000` | the API, for the authorization checks        |

They are deliberately excluded from `pnpm test` and from the default CI job,
which would otherwise need a database and two long-running servers to run a unit
test suite.
