"use client";

import { EmptyState } from "@/components/ui/empty-state";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { formatDate } from "@/lib/format";
import type { TrainingSession } from "@/lib/types";

export function SessionTable({ sessions }: { sessions: TrainingSession[] }) {
  if (sessions.length === 0) {
    return (
      <EmptyState
        title="No sessions recorded"
        description="Sessions appear here once a TrackMan export for this athlete is imported."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[580px] text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <th className="py-2 pr-4 font-medium">Date</th>
            <th className="py-2 pr-4 font-medium">Type</th>
            <th className="py-2 pr-4 text-right font-medium">Pitches</th>
            <th className="py-2 pr-4 text-right font-medium">Batted balls</th>
            <th className="py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sessions.map((session) => (
            <tr key={session.id} className="transition-colors hover:bg-muted/30">
              <td className="py-2.5 pr-4 font-medium">
                {formatDate(session.session_date)}
              </td>
              <td className="py-2.5 pr-4 text-muted-foreground">
                {session.session_type ?? "—"}
              </td>
              <td className="tabular py-2.5 pr-4 text-right">
                {session.pitch_count || "—"}
              </td>
              <td className="tabular py-2.5 pr-4 text-right">
                {session.hit_count || "—"}
              </td>
              <td className="py-2.5">
                <SourceStatusBadge status={session.source_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
