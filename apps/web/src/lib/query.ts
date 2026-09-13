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
          // Never retry an authorization failure: the answer will not change,
          // and repeatedly probing another athlete's data is exactly what the
          // server is refusing.
          if (
            error instanceof ApiError &&
            (error.isForbidden || error.isUnauthenticated)
          ) {
            return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}
