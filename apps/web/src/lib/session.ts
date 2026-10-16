/**
 * Session credential storage.
 *
 * The token is an opaque bearer token issued by `POST /auth/login`. It carries
 * no permissions of its own: the server resolves it to a user and decides what
 * that user may see on every request. Clearing it here signs this browser out.
 */

import type { QueryClient } from "@tanstack/react-query";

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
 * Switch the signed-in person, cache and all.
 *
 * Every cached query was answered *for the previous credential*. Keeping any of
 * it across a sign-in would put one person's name, roster or report on screen
 * for another -- which is how the sidebar ended up greeting the previous
 * athlete while showing the new one's session. Clearing is the only safe
 * default: there is no query here whose answer is the same for two people.
 */
export function startSession(queryClient: QueryClient, token: string): void {
  queryClient.clear();
  setToken(token);
}

/** The same rule in reverse: nothing cached outlives the session it came from. */
export function endSession(queryClient: QueryClient): void {
  clearToken();
  queryClient.clear();
}
