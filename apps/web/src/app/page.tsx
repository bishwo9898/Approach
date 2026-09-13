"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-api";

/** Sends each role to the dashboard built for it. */
export default function HomePage() {
  const router = useRouter();
  const { data: user, isError, isLoading } = useCurrentUser();

  useEffect(() => {
    if (isError) router.replace("/login");
    else if (user) router.replace(user.role === "PLAYER" ? "/player" : "/coach");
  }, [user, isError, router]);

  return (
    <div className="mx-auto max-w-md space-y-3 p-10">
      {isLoading ? <Skeleton className="h-8 w-full" /> : null}
    </div>
  );
}
