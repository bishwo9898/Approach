"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { HittingPeriodView } from "@/components/hitting/period-summary";
import { PeriodPicker, type View } from "@/components/hitting/period-picker";
import { HittingSessionReport } from "@/components/hitting/session-report";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useHittingPeriod,
  useHittingSession,
  useHittingSessions,
  useLatestHittingSession,
  usePlayer,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import type { TimeRange } from "@/lib/types";

/** A coach's view of one athlete -- the same report the athlete sees. */
export default function CoachPlayerPage() {
  const { playerId } = useParams<{ playerId: string }>();
  const player = usePlayer(playerId);
  const [view, setView] = useState<View>("session");

  const sessions = useHittingSessions(playerId);
  const latest = useLatestHittingSession(playerId);
  const [selected, setSelected] = useState<string | null>(null);
  const chosen = useHittingSession(selected, playerId);
  const period = useHittingPeriod(
    view === "session" ? null : (view as TimeRange),
    playerId,
  );

  const report = selected ? chosen.data : latest.data;
  const all = sessions.data ?? [];
  const neverBatted = !latest.isLoading && !report && all.length === 0;

  if (latest.isLoading && !report) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const heading = player.data?.display_name ?? "Athlete";
  const subtitle = [
    player.data?.position,
    player.data?.graduation_year ? `Class of ${player.data.graduation_year}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
        {subtitle ? <p className="text-sm text-muted-foreground">{subtitle}</p> : null}
      </header>

      {neverBatted ? (
        <EmptyState
          title="Nothing to show yet"
          description="No TrackMan session has been imported for this athlete. Import one from Data Health and their report appears here."
        />
      ) : (
        <>
          <PeriodPicker value={view} onChange={setView} />

          {view === "session" ? (
            <>
              {all.length > 1 ? (
                <div className="flex flex-wrap gap-1">
                  {all.map((session, index) => {
                    const isActive = selected
                      ? selected === session.session_id
                      : index === 0;
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
        </>
      )}
    </div>
  );
}
