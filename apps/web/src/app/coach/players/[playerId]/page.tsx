"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { HittingSessionReport } from "@/components/hitting/session-report";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useHittingSession,
  useHittingSessions,
  useLatestHittingSession,
  usePlayer,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";

/** A coach's view of one athlete -- the same report the athlete sees. */
export default function CoachPlayerPage() {
  const { playerId } = useParams<{ playerId: string }>();
  const player = usePlayer(playerId);
  const sessions = useHittingSessions(playerId);
  const latest = useLatestHittingSession(playerId);
  const [selected, setSelected] = useState<string | null>(null);

  const chosen = useHittingSession(selected, playerId);
  const report = selected ? chosen.data : latest.data;

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
  const all = sessions.data ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
        {subtitle ? <p className="text-sm text-muted-foreground">{subtitle}</p> : null}
      </header>

      {!report ? (
        <EmptyState
          title="No batting sessions imported yet"
          description="Import a TrackMan export for this athlete from Data Health, and their report appears here."
        />
      ) : (
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
          <HittingSessionReport report={report} />
        </>
      )}
    </div>
  );
}
