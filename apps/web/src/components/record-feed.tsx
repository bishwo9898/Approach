"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/ui/icons";
import { EmptyState } from "@/components/ui/empty-state";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { formatDate, formatDelta, formatMeasurement } from "@/lib/format";
import type { PersonalRecordEvent } from "@/lib/types";

/** Newest records across the roster -- what a coach scans first. */
export function RecordFeed({
  events,
  linkToPlayer = true,
}: {
  events: PersonalRecordEvent[];
  linkToPlayer?: boolean;
}) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No new records in this period"
        description="Records appear here as soon as a TrackMan session is imported."
      />
    );
  }

  return (
    <ul className="divide-y divide-border">
      {events.map((event) => {
        // A first record has no delta -- there was nothing to improve on.
        const delta = formatDelta(event.delta, event.display_precision);
        const name = linkToPlayer ? (
          <Link
            href={`/coach/players/${event.player_id}`}
            className="font-medium hover:underline"
          >
            {event.player_display_name}
          </Link>
        ) : (
          <span className="font-medium">{event.player_display_name}</span>
        );

        return (
          <li key={event.id} className="flex items-center gap-3 py-3.5 text-sm">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600 ring-1 ring-amber-100">
              <Icon name="trophy" className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate">{name}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                {event.metric_display_name} · {formatDate(event.achieved_on)} · n=
                {event.sample_size}
              </div>
            </div>
            <div className="tabular text-right">
              <div className="font-semibold">
                {formatMeasurement(event.new_value, event.unit, event.display_precision)}
              </div>
              {delta ? (
                <div className="text-xs text-positive">{delta}</div>
              ) : (
                <div className="text-xs text-muted-foreground">first</div>
              )}
            </div>
            <div className="hidden w-24 shrink-0 flex-col items-end gap-1 sm:flex">
              <Badge variant="record">NEW PR</Badge>
              <SourceStatusBadge status={event.source_status} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
