"use client";

import { useState } from "react";

import { HittingPeriodView } from "@/components/hitting/period-summary";
import { PeriodPicker, type View } from "@/components/hitting/period-picker";
import { HittingSessionReport } from "@/components/hitting/session-report";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCurrentUser,
  useHittingPeriod,
  useHittingSession,
  useHittingSessions,
  useLatestHittingSession,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import type { TimeRange } from "@/lib/types";

/**
 * The athlete's own page: their last session, or how a period has gone.
 *
 * Every request here is scoped to the caller by the server, so this page never
 * sends an athlete id and there is none to tamper with.
 *
 * The period views are always offered, including before there is enough data
 * to fill them. They say what they do not know rather than being hidden, so
 * the page an athlete sees in week one is the page they see in month six.
 */
export default function PlayerPage() {
  const user = useCurrentUser();
  const [view, setView] = useState<View>("session");

  const sessions = useHittingSessions();
  const latest = useLatestHittingSession();
  const [selected, setSelected] = useState<string | null>(null);
  const chosen = useHittingSession(selected);
  const period = useHittingPeriod(view === "session" ? null : (view as TimeRange));

  const report = selected ? chosen.data : latest.data;
  const loadingSession = latest.isLoading || sessions.isLoading || chosen.isLoading;
  const firstName = user.data?.display_name.split(" ")[0] ?? "";
  const all = sessions.data ?? [];

  // "No sessions at all" is a different statement from "none in this window",
  // and only the first one makes the period controls pointless.
  const neverBatted = !loadingSession && !report && all.length === 0;

  if (loadingSession && !report) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (neverBatted) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {firstName ? `Hi ${firstName}` : "Your sessions"}
        </h1>
        <EmptyState
          title="Nothing to show yet"
          description="Once your coach imports a TrackMan session you batted in, your report shows up here."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {firstName ? (
        <p className="text-sm text-muted-foreground">
          Hi {firstName} —{" "}
          {view === "session" ? "here is your last session." : "here is how it is going."}
        </p>
      ) : null}

      <PeriodPicker value={view} onChange={setView} />

      {view === "session" ? (
        <>
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
          {report ? <HittingSessionReport report={report} /> : null}
        </>
      ) : period.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : period.data ? (
        <HittingPeriodView summary={period.data} />
      ) : null}
    </div>
  );
}
