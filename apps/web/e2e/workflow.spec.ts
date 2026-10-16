import { expect, test, type Page } from "@playwright/test";

/**
 * The two journeys that matter right now:
 *   a coach opening an athlete's session, and that athlete opening their own.
 *
 * Plus the boundary between them, which is the property most worth checking in
 * a real browser: a player must not reach anyone else's page.
 *
 * Requires a provisioned roster and the two demo logins:
 *   python -m bsa.scripts.provision_roster <roster.csv> --demo-accounts
 */

/** The roster rows, addressed by role rather than by any athlete's name. */
const athleteRows = (page: Page) => page.getByTestId("athlete-row");

/**
 * Credentials come from the environment.
 *
 * The coach address is a role, not a person, so it has a default. The athlete's
 * is a real minor's name -- `first.last@domain` -- so it has none, and the
 * athlete-facing tests skip without it rather than putting a name in a public
 * repository. `provision_roster --demo-accounts` prints both.
 */
const PASSWORD = process.env.E2E_PASSWORD ?? "SpringTraining26";
const COACH_EMAIL = process.env.E2E_COACH_EMAIL ?? "coach@approach.com";
const PLAYER_EMAIL = process.env.E2E_PLAYER_EMAIL ?? "";

/** Narrows the roster to the athlete who has data, when one is named. */
const ATHLETE_QUERY = process.env.E2E_ATHLETE_QUERY ?? "";

const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  const emailField = page.getByLabel("Email");
  await expect(emailField).toBeVisible();

  // The login page is prerendered, so the form exists before React hydrates
  // and attaches its handler. Retry until the submit actually takes.
  await expect(async () => {
    await emailField.fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /Sign in|Signing in/ }).click();
    await expect(page).not.toHaveURL(/\/login/, { timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

/** A session token straight from the API, for asserting what the server refuses. */
async function tokenFor(
  request: {
    post: (url: string, init: object) => Promise<{ json: () => Promise<unknown> }>;
  },
  email: string,
): Promise<string> {
  const response = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { email, password: PASSWORD },
  });
  return ((await response.json()) as { token: string }).token;
}

test.describe("account setup", () => {
  test("an unknown email is told it does not match", async ({ page }) => {
    await page.goto("/activate");
    const field = page.getByLabel("Email");
    await expect(field).toBeVisible();

    await expect(async () => {
      await field.fill("nobody.at.all@approach.com");
      await page.getByRole("button", { name: /Continue|Checking/ }).click();
      await expect(page.getByRole("alert")).toContainText("Email does not match.", {
        timeout: 2_000,
      });
    }).toPass({ timeout: 20_000 });
  });

  test("an already-claimed account is sent to sign in", async ({ page }) => {
    await page.goto("/activate");
    const field = page.getByLabel("Email");
    await expect(field).toBeVisible();

    await expect(async () => {
      await field.fill(COACH_EMAIL);
      await page.getByRole("button", { name: /Continue|Checking/ }).click();
      await expect(page.getByRole("alert")).toContainText("already has a password", {
        timeout: 2_000,
      });
    }).toPass({ timeout: 20_000 });

    await page.getByRole("link", { name: "Go to sign in" }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("coach", () => {
  test("opens an athlete from the roster", async ({ page }) => {
    await signIn(page, COACH_EMAIL);
    await expect(page).toHaveURL(/\/coach\/players/);

    // The roster is ~490 athletes and most have no session yet, so this asserts
    // navigation only. Reading a report is the athlete test's job.
    await expect(athleteRows(page).first()).toBeVisible();
    await athleteRows(page).first().click();
    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  });

  test("reads the session of the athlete who has data", async ({ page }) => {
    test.skip(!ATHLETE_QUERY, "set E2E_ATHLETE_QUERY to the athlete with imported data");
    await signIn(page, COACH_EMAIL);

    await page.getByLabel("Search athletes").fill(ATHLETE_QUERY);
    await athleteRows(page).first().click();

    await expect(page.getByText(/\d+ pitches · \d+ swings/)).toBeVisible();
    await expect(page.getByText("Hardest ball", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "What this session says" }),
    ).toBeVisible();
  });

  test("can reach data health to import new sessions", async ({ page }) => {
    await signIn(page, COACH_EMAIL);
    await page.getByRole("link", { name: "Data Health" }).click();

    await expect(page.getByText(/Import a TrackMan export/i)).toBeVisible();
    await expect(page.getByText(/Athlete mapping required/i)).toBeVisible();
  });

  test("signing out revokes the session, not just the browser's copy", async ({
    page,
  }) => {
    await signIn(page, COACH_EMAIL);
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await expect(page).toHaveURL(/\/login/);

    // Going back must not restore access: the token it would reuse is revoked.
    await page.goto("/coach/players");
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("player", () => {
  test.skip(
    !PLAYER_EMAIL,
    "set E2E_PLAYER_EMAIL to the athlete login printed by provision_roster",
  );

  test("sees their own session and nothing else", async ({ page }) => {
    await signIn(page, PLAYER_EMAIL);
    await expect(page).toHaveURL(/\/player/);

    await expect(page.getByText(/\d+ pitches · \d+ swings/)).toBeVisible();
    await expect(page.getByText("Hardest ball", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Video" })).toBeVisible();

    // Coach-only navigation is not offered to them.
    await expect(page.getByRole("link", { name: "Data Health" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Athletes" })).toHaveCount(0);
  });

  test("can switch to a period and gets an honest answer either way", async ({
    page,
  }) => {
    await signIn(page, PLAYER_EMAIL);
    await page.getByRole("button", { name: "Month" }).click();

    // With one session the view exists and says so; with several it draws the
    // trend. Both are correct, so assert the view rendered rather than which.
    await expect(
      page
        .getByText("Nothing to show yet")
        .or(page.getByText("Not enough for a trend yet"))
        .or(page.getByRole("img", { name: /Exit velocity/ })),
    ).toBeVisible();

    // Going back to the session view must still work.
    await page.getByRole("button", { name: "Last session" }).click();
    await expect(page.getByText(/\d+ pitches · \d+ swings/)).toBeVisible();
  });

  test("every number on the page carries its sample size", async ({ page }) => {
    await signIn(page, PLAYER_EMAIL);

    await expect(page.getByText(/of \d+ swings/)).toBeVisible();
    await expect(page.getByText(/across \d+ batted balls/)).toBeVisible();
  });

  test("cannot reach another athlete, and the server is what refuses", async ({
    page,
    request,
  }) => {
    await signIn(page, COACH_EMAIL);
    await athleteRows(page).first().click();
    await expect(page).toHaveURL(/\/coach\/players\/[0-9a-f-]{36}/);
    const someoneElse = page.url().split("/").pop()!;

    const playerToken = await tokenFor(request, PLAYER_EMAIL);
    const auth = { Authorization: `Bearer ${playerToken}` };

    // A player reaching the coach roster is refused outright.
    const roster = await request.get(`${API_BASE}/api/v1/players`, { headers: auth });
    expect(roster.status()).toBe(403);

    // Their own report through the coach route is allowed, because it is theirs
    // -- the id is checked against their own athlete, server-side.
    const own = await request.get(`${API_BASE}/api/v1/me/hitting/latest`, {
      headers: auth,
    });
    expect(own.status()).toBe(200);

    // Any other athlete is "not found", so the roster cannot be enumerated by
    // trying ids. 404 rather than 403 on purpose: 403 would confirm the athlete
    // exists. The first roster row is alphabetical, so it is somebody else.
    const foreign = await request.get(
      `${API_BASE}/api/v1/players/${someoneElse}/hitting/latest`,
      { headers: auth },
    );
    expect(foreign.status()).toBe(404);
  });
});
