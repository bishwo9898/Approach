import { expect, test, type Page } from "@playwright/test";

/**
 * The Phase 1 acceptance workflow:
 *   coach signs in → searches an athlete → opens them → inspects analytics.
 *
 * Plus the authorization boundary, which is the property most worth protecting
 * with a real browser: a player must not reach another athlete's page.
 */

async function signIn(page: Page, label: RegExp) {
  await page.goto("/login");
  const account = page.getByRole("button", { name: label });
  await expect(account).toBeVisible();

  // The login page is prerendered, so the button exists in the DOM before React
  // hydrates and attaches its handler. A click that lands in that window focuses
  // the button and does nothing else. Retry until it actually takes.
  await expect(async () => {
    await account.click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

test.describe("coach workflow", () => {
  test("signs in and sees today's activity", async ({ page }) => {
    await signIn(page, /Chris Coach/);

    await expect(page).toHaveURL(/\/coach$/);
    await expect(page.getByRole("heading", { name: "Today" })).toBeVisible();
    await expect(page.getByText("Athletes Trained")).toBeVisible();
    await expect(page.getByText("New PRs")).toBeVisible();
  });

  test("searches an athlete, opens them, and reads their analytics", async ({ page }) => {
    await signIn(page, /Chris Coach/);

    await page.getByLabel("Search athletes").first().fill("Jones");
    const result = page.getByRole("button", { name: /Ryan Jones/ });
    await expect(result).toBeVisible();
    await result.click();

    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { name: "Ryan Jones" })).toBeVisible();

    // Every measurement carries its unit.
    const headline = page.getByText(/\d+\.\d+ mph/).first();
    await expect(headline).toBeVisible();

    // Every aggregate carries its sample size.
    await expect(page.getByText(/^n=\d+$/).first()).toBeVisible();

    // The progression chart renders, labelled with its unit.
    await expect(page.getByText(/in mph · \d+ sessions/)).toBeVisible();
  });

  test("switches time range and metric without losing the athlete", async ({ page }) => {
    await signIn(page, /Chris Coach/);
    await page.getByLabel("Search athletes").first().fill("Jones");
    await page.getByRole("button", { name: /Ryan Jones/ }).click();

    await page.getByRole("button", { name: "90 Days" }).click();
    await expect(page.getByRole("button", { name: "90 Days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("heading", { name: "Ryan Jones" })).toBeVisible();
  });

  test("shows personal records and session history", async ({ page }) => {
    await signIn(page, /Chris Coach/);
    await page.getByLabel("Search athletes").first().fill("Jones");
    await page.getByRole("button", { name: /Ryan Jones/ }).click();

    await page.getByRole("tab", { name: "Personal Records" }).click();
    await expect(page.getByText("Fastball Max Velocity").first()).toBeVisible();

    await page.getByRole("tab", { name: "Sessions" }).click();
    await expect(page.getByRole("columnheader", { name: "Date" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Pitches" })).toBeVisible();
  });

  test("surfaces data health rather than hiding it", async ({ page }) => {
    await signIn(page, /Chris Coach/);
    await page.getByRole("link", { name: "Data Health" }).click();

    await expect(page.getByRole("heading", { name: "Data Health" })).toBeVisible();
    await expect(page.getByText("Athlete Mapping Required")).toBeVisible();
    await expect(page.getByText("Futures Updates Pending")).toBeVisible();
  });
});

test.describe("player access", () => {
  test("a player sees their own dashboard", async ({ page }) => {
    await signIn(page, /Jake Williams/);

    await expect(page).toHaveURL(/\/player$/);
    await expect(page.getByRole("heading", { name: /Welcome, Jake/ })).toBeVisible();
    await expect(page.getByText("Your Personal Records")).toBeVisible();
  });

  test("a player cannot reach another athlete by changing the URL", async ({
    page,
    request,
  }) => {
    // Find another athlete's id as the coach.
    await signIn(page, /Chris Coach/);
    await page.getByLabel("Search athletes").first().fill("Jones");
    await page.getByRole("button", { name: /Ryan Jones/ }).click();
    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}$/);
    const otherId = page.url().split("/").pop()!;

    // The server refuses, not just the UI: assert the API directly.
    const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
    const forbidden = await request.get(`${apiBase}/api/v1/players/${otherId}`, {
      headers: { Authorization: "Bearer dev|player" },
    });
    expect(forbidden.status()).toBe(403);

    // And the page itself does not render their data.
    await signIn(page, /Jake Williams/);
    await page.goto(`/coach/players/${otherId}`);
    await expect(page.getByRole("heading", { name: "Ryan Jones" })).toHaveCount(0);
  });
});
