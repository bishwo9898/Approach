"use client";

import { useState } from "react";

import { HittingSessionReport } from "@/components/hitting/session-report";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCurrentUser,
  useHittingSession,
  useHittingSessions,
  useLatestHittingSession,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";

/**
 * The athlete's own page: their most recent session, and nothing else.
 *
 * Every request here is scoped to the caller by the server, so this page never
 * sends an athlete id and there is none to tamper with.
 *
 * The session picker appears only once there is more than one session. With a
 * single session it would be a control with nothing to choose.
 */
export default function PlayerPage() {
  const user = useCurrentUser();
  const sessions = useHittingSessions();
  const latest = useLatestHittingSession();
  const [selected, setSelected] = useState<string | null>(null);

  const chosen = useHittingSession(selected);
  const report = selected ? chosen.data : latest.data;
  const loading = latest.isLoading || sessions.isLoading || chosen.isLoading;

  const firstName = user.data?.display_name.split(" ")[0] ?? "";

  if (loading && !report) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {firstName ? `Hi ${firstName}` : "Your sessions"}
        </h1>
        <EmptyState
          title="No sessions yet"
          description="Once your coach imports a TrackMan session you batted in, your report shows up here."
        />
      </div>
    );
  }

  const all = sessions.data ?? [];

  return (
    <div className="space-y-6">
      {firstName ? (
        <p className="text-sm text-muted-foreground">
          Hi {firstName} — here is your last session.
        </p>
      ) : null}

      {all.length > 1 ? (
        <div className="flex flex-wrap gap-1">
          {all.map((session, index) => {
            const isActive = selected ? selected === session.session_id : index === 0;
            return (
              <Button
                key={session.session_id}
                size="sm"
                variant={isActive ? "default" : "outline"}
                onClick={() => setSelected(session.session_id)}
              >
                {formatDate(session.session_date)}
              </Button>
            );
          })}
        </div>
      ) : null}

      <HittingSessionReport report={report} />
    </div>
  );
}
