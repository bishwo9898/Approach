"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useCurrentUser } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import type { Role } from "@/lib/types";

/**
 * Routes the viewer to a page their role can use.
 *
 * This is navigation, NOT a security control. Every endpoint behind these pages
 * re-checks the caller's role and athlete scope on the server, so removing this
 * component would make the app confusing, not insecure.
 */
export function AuthGate({
  children,
  allow,
}: {
  children: React.ReactNode;
  allow: Role[];
}) {
  const router = useRouter();
  const { data: user, isLoading, isError, error } = useCurrentUser();

  useEffect(() => {
    // Only a rejected credential sends someone back to sign in. An unreachable
    // API would otherwise bounce them to a login that cannot work either.
    if (isError && !(error instanceof ApiError && error.isUnreachable)) {
      router.replace("/login");
      return;
    }
    if (user && !allow.includes(user.role)) {
      router.replace(user.role === "PLAYER" ? "/player" : "/coach");
    }
  }, [user, isError, error, allow, router]);

  if (isError && error instanceof ApiError && error.isUnreachable) {
    return (
      <div className="grid min-h-screen place-items-center px-6">
        <p className="text-sm text-muted-foreground">
          Can&apos;t reach the server. It may be starting up — refresh shortly.
        </p>
      </div>
    );
  }

  if (isLoading || !user) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!allow.includes(user.role)) return null;
  return <>{children}</>;
}
