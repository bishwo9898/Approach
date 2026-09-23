/**
 * Session credential storage.
 *
 * Phase 1 uses the backend's development auth provider: a readable, seeded
 * token that identifies a user. It is NOT a secret and carries no permissions
 * of its own -- the server looks the user up and decides what they may see.
 *
 * When Clerk is wired up this module is the only thing that changes: `getToken`
 * returns Clerk's session token and the login page goes away.
 */

const STORAGE_KEY = "bsa.session.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). Treat that
    // as signed out rather than crashing the app.
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, token.trim());
  } catch {
    /* ignore */
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * The two accounts we are testing with.
 *
 * Created by `python -m bsa.scripts.seed_athlete`. The player account is
 * linked to whichever athlete the loaded export names, so no real name lives
 * in this repository. These are identities rather
 * than credentials: the development auth provider treats the token as the
 * subject, and refuses to run outside development. Clerk replaces all of this
 * before any real sign-in exists.
 */
export const ACCOUNTS = [
  {
    token: "dev|coach",
    label: "Coach",
    role: "COACH" as const,
    blurb: "See every athlete and import new sessions",
  },
  {
    token: "dev|player",
    label: "Player",
    role: "PLAYER" as const,
    blurb: "See only your own sessions",
  },
] as const;
