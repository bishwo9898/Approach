import type { FullConfig } from "@playwright/test";

/**
 * Warm the dev server and check the backend before any test runs.
 *
 * These tests drive `next dev`, which compiles a route on its first request.
 * Without warming, whichever test happens to run first races that compile and
 * fails for reasons that have nothing to do with the application — a flaky
 * suite that nobody trusts is worse than no suite.
 *
 * It also fails fast and loudly when the API or seed data is missing, rather
 * than letting seven tests time out one by one.
 */
const ROUTES = ["/login", "/coach", "/coach/players", "/coach/operations", "/player"];

async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL =
    config.projects[0]?.use.baseURL ??
    process.env.E2E_BASE_URL ??
    "http://localhost:3000";
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

  const health = await fetch(`${apiBase}/health`).catch(() => null);
  if (!health?.ok) {
    throw new Error(
      `The API is not reachable at ${apiBase}. Start it with:\n` +
        `  cd apps/api && .venv/bin/uvicorn bsa.api.app:app --port 8000`,
    );
  }

  const me = await fetch(`${apiBase}/api/v1/me`, {
    headers: { Authorization: `Bearer ${process.env.E2E_COACH_PASSCODE ?? "coach"}` },
  }).catch(() => null);
  if (!me?.ok) {
    throw new Error(
      "The testing accounts are missing. Run:\n" +
        '  cd apps/api && .venv/bin/python -m bsa.scripts.seed_athlete "<export>.csv"',
    );
  }

  // The reports need a real session behind them, and an empty database would
  // fail every test with a timeout rather than a reason.
  const report = await fetch(`${apiBase}/api/v1/me/hitting/latest`, {
    headers: { Authorization: `Bearer ${process.env.E2E_PLAYER_PASSCODE ?? "player"}` },
  }).catch(() => null);
  if (!report?.ok) {
    throw new Error("No batting session is loaded. Run seed_athlete with a real export.");
  }

  for (const route of ROUTES) {
    await fetch(`${baseURL}${route}`).catch(() => null);
  }
}

export default globalSetup;
