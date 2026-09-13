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

/** The tokens the seed script creates. Development convenience only. */
export const DEV_TOKENS = [
  { token: "dev|coach", label: "Chris Coach", role: "COACH" },
  { token: "dev|admin", label: "Dana Admin", role: "ADMIN" },
  { token: "dev|player", label: "Jake Williams", role: "PLAYER" },
  { token: "dev|player2", label: "Marcus Cole", role: "PLAYER" },
] as const;
