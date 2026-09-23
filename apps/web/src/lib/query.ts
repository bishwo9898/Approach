"use client";

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Never retry a refused credential: the answer will not change, and
          // repeatedly probing another athlete's data is exactly what the
          // server is refusing.
          if (
            error instanceof ApiError &&
            (error.isForbidden || error.isUnauthenticated)
          ) {
            return false;
          }
          // A hosted API on a free tier sleeps and takes most of a minute to
          // wake. Keep trying rather than showing an error the user can do
          // nothing about; the backoff below spans roughly that long.
          if (error instanceof ApiError && error.isUnreachable) {
            return failureCount < 6;
          }
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 10_000),
      },
    },
  });
}
