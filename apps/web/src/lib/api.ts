/**
 * Typed API client.
 *
 * One place that knows how to reach the backend and how it reports errors. No
 * component builds a URL or reads a token itself.
 *
 * Note on credentials: the token here is the *user's* session credential. No
 * vendor secret (TrackMan, Futures) ever reaches the browser -- those live
 * server-side only, which is why there is no integration config in this client.
 */

import { getToken } from "@/lib/session";
import type {
  ActivationTarget,
  CreatePlayerInput,
  HittingPeriodSummary,
  HittingReport,
  HittingSessionSummary,
  CurrentUser,
  ImportDetail,
  ImportResult,
  ImportSummary,
  IntegrationHealth,
  MetricDefinition,
  MetricSeries,
  PersonalRecord,
  PersonalRecordEvent,
  PlayerOverview,
  PlayerSummary,
  ResolveIdentityResult,
  SignIn,
  SyncJob,
  TimeRange,
  TodaySnapshot,
  TrainingSession,
  UnresolvedIdentity,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    /** Extra fields the server attached, e.g. the list of password problems. */
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  /**
   * The request never reached the API.
   *
   * Status 0 is reserved for this. It matters because a hosted API on a
   * free tier sleeps and takes the better part of a minute to wake -- the
   * difference between "email or password is incorrect" and "the server is
   * waking up" is the difference between someone retyping a password that was
   * correct all along and waiting ten seconds.
   */
  get isUnreachable(): boolean {
    return this.status === 0;
  }

  /** The caller is not signed in, or their credential is no longer valid. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** Nothing of this kind exists -- an unrecognized email, an athlete with no sessions. */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** Too many attempts, or an account locked by them. Always temporary. */
  get isThrottled(): boolean {
    return this.status === 429;
  }

  /**
   * Problems the server found with a submitted password, in its words.
   *
   * Returned as a list so the form can show every reason at once. The server's
   * policy is the only one that decides; the browser's copy is a hint.
   */
  get problems(): string[] {
    const found = (this.details as { problems?: unknown }).problems;
    return Array.isArray(found)
      ? found.filter((p): p is string => typeof p === "string")
      : [];
  }

  /** Signed in, but not permitted. Never retry these. */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    // fetch rejects only when the request never completed: the API is down,
    // asleep, or blocked by CORS. Never a credential problem.
    throw new ApiError(0, "unreachable", "Could not reach the server.");
  }

  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed with status ${response.status}`;
    let details: Record<string, unknown> = {};
    try {
      const body = (await response.json()) as {
        error?: { code: string; message: string } & Record<string, unknown>;
        detail?: { msg?: string }[];
      };
      if (body.error) {
        const { code: errorCode, message: errorMessage, ...rest } = body.error;
        code = errorCode;
        message = errorMessage;
        details = rest;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        // FastAPI's own request-validation shape, e.g. a malformed email.
        code = "validation_error";
        message = body.detail[0].msg.replace(/^Value error, /, "");
      }
    } catch {
      // A non-JSON error body (a proxy or gateway page) still gets a usable message.
    }
    throw new ApiError(response.status, code, message, details);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const qs = (params: Record<string, string | number | boolean | undefined>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
};

export const api = {
  me: () => request<CurrentUser>("/api/v1/me"),

  // -- account setup and sign-in -------------------------------------------
  //
  // Accounts are provisioned by the facility from its roster, so there is no
  // "register" call. An athlete proves which provisioned account is theirs,
  // then chooses a password for it.

  /** Check an email against the roster. Throws 404 when it does not match. */
  checkEmail: (email: string, code?: string) =>
    request<ActivationTarget>("/api/v1/auth/activation/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code: code || null }),
    }),

  /** Set the account's first password. Does not sign anyone in. */
  createPassword: (input: {
    email: string;
    password: string;
    passwordConfirmation: string;
    code?: string;
  }) =>
    request<void>("/api/v1/auth/activation/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: input.email,
        code: input.code || null,
        password: input.password,
        password_confirmation: input.passwordConfirmation,
      }),
    }),

  login: (email: string, password: string) =>
    request<SignIn>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  /** Revoke this session server-side. Other devices stay signed in. */
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  // -- coach --------------------------------------------------------------
  today: (date?: string) =>
    request<TodaySnapshot>(`/api/v1/dashboard/today${qs({ date })}`),

  recentRecords: (days = 14, limit = 25) =>
    request<PersonalRecordEvent[]>(`/api/v1/prs/recent${qs({ days, limit })}`),

  integrationStatus: () => request<IntegrationHealth>("/api/v1/integrations/status"),

  searchPlayers: (q?: string, limit = 500) =>
    request<PlayerSummary[]>(`/api/v1/players${qs({ q, limit })}`),

  player: (playerId: string) => request<PlayerSummary>(`/api/v1/players/${playerId}`),

  /** Add an athlete to the roster. Does not map them to any vendor identity. */
  createPlayer: (input: CreatePlayerInput) =>
    request<PlayerSummary>("/api/v1/players", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),

  playerOverview: (playerId: string, range: TimeRange = "30d", headlineOnly = true) =>
    request<PlayerOverview>(
      `/api/v1/players/${playerId}/overview${qs({ range, headline_only: headlineOnly })}`,
    ),

  playerSeries: (playerId: string, metricKey: string, range: TimeRange = "90d") =>
    request<MetricSeries>(
      `/api/v1/players/${playerId}/metrics/${metricKey}/series${qs({ range })}`,
    ),

  playerRecords: (playerId: string) =>
    request<PersonalRecord[]>(`/api/v1/players/${playerId}/prs`),

  playerRecordHistory: (playerId: string, metricKey: string) =>
    request<PersonalRecordEvent[]>(
      `/api/v1/players/${playerId}/prs/${metricKey}/history`,
    ),

  playerSessions: (playerId: string, limit = 20) =>
    request<TrainingSession[]>(`/api/v1/players/${playerId}/sessions${qs({ limit })}`),

  sessions: (date?: string, limit = 50) =>
    request<TrainingSession[]>(`/api/v1/sessions${qs({ date, limit })}`),

  metrics: () => request<MetricDefinition[]>("/api/v1/metrics"),

  unresolvedIdentities: () =>
    request<UnresolvedIdentity[]>("/api/v1/identity/unresolved"),

  /** Map a vendor athlete to one of ours, and recover their held data. */
  resolveIdentity: (itemId: string, playerId: string, note?: string) =>
    request<ResolveIdentityResult>(`/api/v1/identity/unresolved/${itemId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId, note, reprocess: true }),
    }),

  imports: (limit = 25) => request<ImportSummary[]>(`/api/v1/imports${qs({ limit })}`),

  importDetail: (importId: string) =>
    request<ImportDetail>(`/api/v1/imports/${importId}`),

  reprocessImport: (importId: string) =>
    request<ImportResult>(`/api/v1/imports/${importId}/reprocess`, { method: "POST" }),

  uploadTrackmanCsv: (file: File, force = false) => {
    const form = new FormData();
    form.append("file", file);
    // Content-Type is deliberately not set: the browser must add the multipart
    // boundary itself.
    return request<ImportResult>(`/api/v1/imports/trackman/csv${qs({ force })}`, {
      method: "POST",
      body: form,
    });
  },

  pendingFuturesUpdates: () => request<SyncJob[]>("/api/v1/sync/futures/pending"),

  markFuturesUpdated: (jobId: string) =>
    request<SyncJob>(`/api/v1/sync/futures/${jobId}/mark-updated`, { method: "POST" }),

  // -- hitting session reports --------------------------------------------
  myLatestHittingSession: () => request<HittingReport>("/api/v1/me/hitting/latest"),

  myHittingSessions: () =>
    request<HittingSessionSummary[]>("/api/v1/me/hitting/sessions"),

  myHittingSession: (sessionId: string) =>
    request<HittingReport>(`/api/v1/me/hitting/sessions/${sessionId}`),

  /** How an athlete has hit over a window. Answers even when the window is empty. */
  myHittingPeriod: (range: TimeRange = "30d") =>
    request<HittingPeriodSummary>(`/api/v1/me/hitting/summary${qs({ range })}`),

  hittingPeriod: (playerId: string, range: TimeRange = "30d") =>
    request<HittingPeriodSummary>(
      `/api/v1/players/${playerId}/hitting/summary${qs({ range })}`,
    ),

  latestHittingSession: (playerId: string) =>
    request<HittingReport>(`/api/v1/players/${playerId}/hitting/latest`),

  hittingSessions: (playerId: string) =>
    request<HittingSessionSummary[]>(`/api/v1/players/${playerId}/hitting/sessions`),

  hittingSession: (playerId: string, sessionId: string) =>
    request<HittingReport>(`/api/v1/players/${playerId}/hitting/sessions/${sessionId}`),

  // -- player -------------------------------------------------------------
  myOverview: (range: TimeRange = "30d") =>
    request<PlayerOverview>(`/api/v1/me/overview${qs({ range })}`),

  myRecords: () => request<PersonalRecord[]>("/api/v1/me/prs"),

  mySessions: (limit = 20) =>
    request<TrainingSession[]>(`/api/v1/me/sessions${qs({ limit })}`),
};
