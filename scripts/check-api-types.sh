#!/usr/bin/env bash
# Fails if the committed OpenAPI document or the generated frontend types are
# stale. Run in CI so a backend schema change cannot silently diverge from the
# types the browser was built against.
set -euo pipefail

cd "$(dirname "$0")/.."

apps/api/.venv/bin/python -m bsa.scripts.dump_openapi >/dev/null 2>&1 \
  || (cd apps/api && python -m bsa.scripts.dump_openapi >/dev/null)
pnpm --filter @bsa/web gen:api >/dev/null

if ! git diff --quiet -- packages/shared/openapi.json apps/web/src/lib/api-types.ts; then
  echo "::error::API types are stale. Run:"
  echo "  cd apps/api && .venv/bin/python -m bsa.scripts.dump_openapi"
  echo "  pnpm --filter @bsa/web gen:api"
  git --no-pager diff --stat -- packages/shared/openapi.json apps/web/src/lib/api-types.ts
  exit 1
fi

echo "API types are in sync."
