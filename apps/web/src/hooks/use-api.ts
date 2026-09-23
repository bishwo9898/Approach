"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { CreatePlayerInput } from "@/lib/types";

/**
 * Server state lives in TanStack Query, not in component state.
 *
 * Query keys mirror the API shape so an invalidation after a mutation is
 * obvious rather than a guess.
 */

export const useCurrentUser = () =>
  useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 5 * 60_000 });

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

export const usePlayer = (playerId: string) =>
  useQuery({
    queryKey: ["players", playerId],
    queryFn: () => api.player(playerId),
    enabled: Boolean(playerId),
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

/**
 * The hitting report is the athlete-facing view. `playerId` is omitted for a
 * player looking at themselves -- those routes take no id at all, so there is
 * nothing for them to tamper with.
 */
export const useLatestHittingSession = (playerId?: string) =>
  useQuery({
    queryKey: ["hitting", playerId ?? "me", "latest"],
    queryFn: () =>
      playerId ? api.latestHittingSession(playerId) : api.myLatestHittingSession(),
    retry: false,
  });

export const useHittingSessions = (playerId?: string) =>
  useQuery({
    queryKey: ["hitting", playerId ?? "me", "sessions"],
    queryFn: () => (playerId ? api.hittingSessions(playerId) : api.myHittingSessions()),
  });

export const useHittingSession = (sessionId: string | null, playerId?: string) =>
  useQuery({
    queryKey: ["hitting", playerId ?? "me", "session", sessionId],
    queryFn: () =>
      playerId
        ? api.hittingSession(playerId, sessionId as string)
        : api.myHittingSession(sessionId as string),
    enabled: Boolean(sessionId),
  });

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
