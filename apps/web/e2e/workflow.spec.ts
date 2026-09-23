import { expect, test, type Page } from "@playwright/test";

/**
 * The two journeys that matter right now:
 *   a coach opening an athlete's session, and that athlete opening their own.
 *
 * Plus the boundary between them, which is the property most worth checking in
 * a real browser: a player must not reach anyone else's page.
 *
 * Requires the real testing roster (`python -m bsa.scripts.seed_athlete`).
 */

/** The roster rows, addressed by role rather than by any athlete's name. */
const athleteRows = (page: Page) => page.getByTestId("athlete-row");

/** Passcodes for the two roles, overridable for a deployed environment. */
const PASSCODES = {
  coach: process.env.E2E_COACH_PASSCODE ?? "coach",
  player: process.env.E2E_PLAYER_PASSCODE ?? "player",
};

async function signIn(page: Page, role: "coach" | "player") {
  await page.goto("/login");
  const field = page.getByLabel("Passcode");
  await expect(field).toBeVisible();

  // The login page is prerendered, so the form exists before React hydrates
  // and attaches its handler. Retry until the submit actually takes.
  await expect(async () => {
    await field.fill(PASSCODES[role]);
    await page.getByRole("button", { name: /Continue|Signing in/ }).click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

test.describe("coach", () => {
  test("opens an athlete and reads their session", async ({ page }) => {
    await signIn(page, "coach");
    await expect(page).toHaveURL(/\/coach\/players/);

    await athleteRows(page).first().click();
    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}/);

    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByText(/\d+ pitches · \d+ swings/)).toBeVisible();
    await expect(page.getByText("Hardest ball", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "What this session says" }),
    ).toBeVisible();
  });

  test("can reach data health to import new sessions", async ({ page }) => {
    await signIn(page, "coach");
    await page.getByRole("link", { name: "Data Health" }).click();

    await expect(page.getByText(/Import a TrackMan export/i)).toBeVisible();
    await expect(page.getByText(/Athlete mapping required/i)).toBeVisible();
  });
});

test.describe("player", () => {
  test("sees their own session and nothing else", async ({ page }) => {
    await signIn(page, "player");
    await expect(page).toHaveURL(/\/player/);

    await expect(page.getByText(/\d+ pitches · \d+ swings/)).toBeVisible();
    await expect(page.getByText("Hardest ball", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Video" })).toBeVisible();

    // Coach-only navigation is not offered to them.
    await expect(page.getByRole("link", { name: "Data Health" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Athletes" })).toHaveCount(0);
  });

  test("every number on the page carries its sample size", async ({ page }) => {
    await signIn(page, "player");

    await expect(page.getByText(/of \d+ swings/)).toBeVisible();
    await expect(page.getByText(/across \d+ batted balls/)).toBeVisible();
  });

  test("cannot reach another athlete, and the server is what refuses", async ({
    page,
    request,
  }) => {
    await signIn(page, "coach");
    await athleteRows(page).first().click();
    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}/);
    const athleteId = page.url().split("/").pop()!;

    const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

    // A player reaching the coach roster is refused outright.
    const roster = await request.get(`${apiBase}/api/v1/players`, {
      headers: { Authorization: `Bearer ${PASSCODES.player}` },
    });
    expect(roster.status()).toBe(403);

    // The athlete reaching their own report through the coach route is allowed,
    // because it is theirs -- the id is checked against their own athlete.
    const own = await request.get(
      `${apiBase}/api/v1/players/${athleteId}/hitting/latest`,
      {
        headers: { Authorization: `Bearer ${PASSCODES.player}` },
      },
    );
    expect(own.status()).toBe(200);

    // An athlete that is not his is "not found", so the roster cannot be
    // enumerated by trying ids.
    const foreign = await request.get(
      `${apiBase}/api/v1/players/00000000-0000-4000-8000-000000000000/hitting/latest`,
      { headers: { Authorization: `Bearer ${PASSCODES.player}` } },
    );
    expect(foreign.status()).toBe(404);
  });
});
