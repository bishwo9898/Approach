"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useCurrentUser } from "@/hooks/use-api";
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
  const { data: user, isLoading, isError } = useCurrentUser();

  useEffect(() => {
    if (isError) {
      router.replace("/login");
      return;
    }
    if (user && !allow.includes(user.role)) {
      router.replace(user.role === "PLAYER" ? "/player" : "/coach");
    }
  }, [user, isError, allow, router]);

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
