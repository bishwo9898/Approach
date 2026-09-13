import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a real stack: the FastAPI backend on :8000 with
 * seeded synthetic data, and the Next.js app on :3000.
 *
 * They are not run by `pnpm test` and are not part of the default CI job,
 * because they need a seeded database. See e2e/README.md.
 */
export default defineConfig({
  testDir: "./e2e",
  // Compiles every route and verifies the backend before the first test, so no
  // test races `next dev`'s first-request compile.
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
