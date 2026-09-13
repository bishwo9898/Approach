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
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The caller is not signed in, or their credential is no longer valid. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as {
        error?: { code: string; message: string };
      };
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // A non-JSON error body (a proxy or gateway page) still gets a usable message.
    }
    throw new ApiError(response.status, code, message);
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

  // -- coach --------------------------------------------------------------
  today: (date?: string) =>
    request<TodaySnapshot>(`/api/v1/dashboard/today${qs({ date })}`),

  recentRecords: (days = 14, limit = 25) =>
    request<PersonalRecordEvent[]>(`/api/v1/prs/recent${qs({ days, limit })}`),

  integrationStatus: () => request<IntegrationHealth>("/api/v1/integrations/status"),

  searchPlayers: (q?: string, limit = 50) =>
    request<PlayerSummary[]>(`/api/v1/players${qs({ q, limit })}`),

  player: (playerId: string) => request<PlayerSummary>(`/api/v1/players/${playerId}`),

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

  // -- player -------------------------------------------------------------
  myOverview: (range: TimeRange = "30d") =>
    request<PlayerOverview>(`/api/v1/me/overview${qs({ range })}`),

  myRecords: () => request<PersonalRecord[]>("/api/v1/me/prs"),

  mySessions: (limit = 20) =>
    request<TrainingSession[]>(`/api/v1/me/sessions${qs({ limit })}`),
};
