"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { CreatePlayerInput, TimeRange } from "@/lib/types";

/**
 * Server state lives in TanStack Query, not in component state.
 *
 * Query keys mirror the API shape so an invalidation after a mutation is
 * obvious rather than a guess.
 */

export const useCurrentUser = () =>
  useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 5 * 60_000 });

export const useToday = (date?: string) =>
  useQuery({ queryKey: ["dashboard", "today", date], queryFn: () => api.today(date) });

export const useRecentRecords = (days = 14, limit = 25) =>
  useQuery({
    queryKey: ["prs", "recent", days, limit],
    queryFn: () => api.recentRecords(days, limit),
  });

export const useIntegrationStatus = () =>
  useQuery({
    queryKey: ["integrations", "status"],
    queryFn: api.integrationStatus,
    // Operational health should not look fresher than it is.
    staleTime: 15_000,
  });

export const usePlayerSearch = (q: string) =>
  useQuery({
    queryKey: ["players", "search", q],
    queryFn: () => api.searchPlayers(q || undefined),
  });

export const usePlayerOverview = (playerId: string, range: TimeRange) =>
  useQuery({
    queryKey: ["players", playerId, "overview", range],
    queryFn: () => api.playerOverview(playerId, range),
    enabled: Boolean(playerId),
  });

export const usePlayerSeries = (
  playerId: string,
  metricKey: string | undefined,
  range: TimeRange,
) =>
  useQuery({
    queryKey: ["players", playerId, "series", metricKey, range],
    queryFn: () => api.playerSeries(playerId, metricKey as string, range),
    enabled: Boolean(playerId && metricKey),
  });

export const usePlayerRecords = (playerId: string) =>
  useQuery({
    queryKey: ["players", playerId, "prs"],
    queryFn: () => api.playerRecords(playerId),
    enabled: Boolean(playerId),
  });

export const usePlayerSessions = (playerId: string, limit = 20) =>
  useQuery({
    queryKey: ["players", playerId, "sessions", limit],
    queryFn: () => api.playerSessions(playerId, limit),
    enabled: Boolean(playerId),
  });

export const useMyOverview = (range: TimeRange) =>
  useQuery({ queryKey: ["me", "overview", range], queryFn: () => api.myOverview(range) });

export const useMyRecords = () =>
  useQuery({ queryKey: ["me", "prs"], queryFn: api.myRecords });

export const useMySessions = (limit = 20) =>
  useQuery({ queryKey: ["me", "sessions", limit], queryFn: () => api.mySessions(limit) });

export const usePendingFuturesUpdates = () =>
  useQuery({
    queryKey: ["sync", "futures", "pending"],
    queryFn: api.pendingFuturesUpdates,
  });

export const useUnresolvedIdentities = () =>
  useQuery({ queryKey: ["identity", "unresolved"], queryFn: api.unresolvedIdentities });

export const useImports = (limit = 25) =>
  useQuery({ queryKey: ["imports", limit], queryFn: () => api.imports(limit) });

export const useImportDetail = (importId: string | null) =>
  useQuery({
    queryKey: ["imports", "detail", importId],
    queryFn: () => api.importDetail(importId as string),
    enabled: Boolean(importId),
  });

/** Everything an import touches, refetched after it changes. */
function invalidateAfterIngest(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of [
    ["imports"],
    ["identity", "unresolved"],
    ["integrations", "status"],
    ["dashboard"],
    ["prs"],
    ["players"],
    ["sync"],
  ]) {
    void queryClient.invalidateQueries({ queryKey: key });
  }
}

export function useUploadCsv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, force }: { file: File; force?: boolean }) =>
      api.uploadTrackmanCsv(file, force),
    onSuccess: () => invalidateAfterIngest(queryClient),
  });
}

export function useReprocessImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) => api.reprocessImport(importId),
    onSuccess: () => invalidateAfterIngest(queryClient),
  });
}

export function useCreatePlayer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreatePlayerInput) => api.createPlayer(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["players"] });
    },
  });
}

export function useResolveIdentity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { itemId: string; playerId: string; note?: string }) =>
      api.resolveIdentity(vars.itemId, vars.playerId, vars.note),
    // Resolution reprocesses held imports, so it can change every derived view.
    onSuccess: () => invalidateAfterIngest(queryClient),
  });
}

export function useMarkFuturesUpdated() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.markFuturesUpdated(jobId),
    onSuccess: () => {
      // The worklist and the health panel both change; refetch both.
      void queryClient.invalidateQueries({ queryKey: ["sync", "futures", "pending"] });
      void queryClient.invalidateQueries({ queryKey: ["integrations", "status"] });
    },
  });
}
