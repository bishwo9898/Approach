#!/usr/bin/env bash
# One-command local setup: dependencies, database schema, and synthetic data.
#
#   ./scripts/dev-setup.sh
#
# Safe to re-run. Requires Python 3.12+, uv, pnpm, and a PostgreSQL you can
# reach (docker compose up -d db, or a local install).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

say() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
die() { printf "\n\033[31merror: %s\033[0m\n" "$1" >&2; exit 1; }

command -v uv   >/dev/null || die "uv is not installed. See https://docs.astral.sh/uv/"
command -v pnpm >/dev/null || die "pnpm is not installed. Try: corepack enable"

if [ ! -f .env ]; then
  say "Creating .env from .env.example"
  cp .env.example .env
  echo "    Edit .env if your database is not on the default host/port."
fi

say "Installing API dependencies"
cd "$ROOT/apps/api"
[ -d .venv ] || uv venv --python 3.12
uv pip install -e ".[dev]" --quiet

say "Checking the database is reachable"
.venv/bin/python - <<'PY' || die "Could not reach the database. Start one with: docker compose up -d db"
from sqlalchemy import create_engine, text
from bsa.core.config import get_settings
settings = get_settings()
with create_engine(settings.database_url).connect() as c:
    c.execute(text("SELECT 1"))
print(f"    connected to {settings.database_target}")
PY

say "Applying migrations"
.venv/bin/alembic upgrade head

say "Seeding synthetic development data"
.venv/bin/python -m bsa.scripts.seed --reset

say "Installing web dependencies"
cd "$ROOT"
pnpm install --silent

cat <<'DONE'

==> Setup complete. Start the two servers in separate terminals:

    cd apps/api && .venv/bin/uvicorn bsa.api.app:app --reload --port 8000
    pnpm --filter @bsa/web dev

Then open http://localhost:3000 and sign in as Chris Coach.

DONE
