"use client";

import Link from "next/link";

import { RecordFeed } from "@/components/record-feed";
import { PlayerSearch } from "@/components/player-search";
import { StatTile } from "@/components/stat-tile";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { useIntegrationStatus, useRecentRecords, useToday } from "@/hooks/use-api";
import { formatDate, formatRelative } from "@/lib/format";

/** The coach's home: today's activity, new records, and search. */
export default function CoachDashboard() {
  const today = useToday();
  const records = useRecentRecords(14, 12);
  const health = useIntegrationStatus();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Today</h1>
        <p className="text-sm text-muted-foreground">
          {today.data ? formatDate(today.data.on_date) : "Loading activity…"}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {today.isLoading || !today.data ? (
          Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-[104px]" />
          ))
        ) : (
          <>
            <StatTile label="Athletes Trained" value={today.data.athletes_trained} />
            <StatTile label="Sessions" value={today.data.sessions} />
            <StatTile
              label="Tracked Events"
              value={today.data.tracked_events.toLocaleString()}
              hint="pitches and batted balls"
            />
            <StatTile label="New PRs" value={today.data.new_personal_records} />
          </>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Recent Personal Records</CardTitle>
            <CardDescription>Last 14 days across the roster</CardDescription>
          </CardHeader>
          <CardContent>
            {records.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }, (_, index) => (
                  <Skeleton key={index} className="h-12 w-full" />
                ))}
              </div>
            ) : (
              <RecordFeed events={records.data ?? []} />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Find an Athlete</CardTitle>
              <CardDescription>Search by first, last or preferred name</CardDescription>
            </CardHeader>
            <CardContent>
              <PlayerSearch />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Data Health</CardTitle>
              <CardDescription>
                <Link href="/coach/operations" className="hover:underline">
                  Open operations →
                </Link>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {health.isLoading || !health.data ? (
                <Skeleton className="h-24 w-full" />
              ) : (
                <>
                  <HealthRow
                    label="Last successful import"
                    value={formatRelative(health.data.last_successful_import_at)}
                  />
                  <HealthRow
                    label="Awaiting verification"
                    value={String(health.data.sessions_awaiting_verification)}
                  />
                  <HealthRow
                    label="Unresolved athletes"
                    value={String(health.data.unresolved_players)}
                    alert={health.data.unresolved_players > 0}
                  />
                  <HealthRow
                    label="Failed imports (7d)"
                    value={String(health.data.failed_imports_7d)}
                    alert={health.data.failed_imports_7d > 0}
                  />
                  <HealthRow
                    label="Futures updates pending"
                    value={String(health.data.futures_updates_pending)}
                    alert={health.data.futures_updates_pending > 0}
                  />
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <TodaySessions />
    </div>
  );
}

function HealthRow({
  label,
  value,
  alert = false,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={
          alert
            ? "tabular text-xs font-semibold text-warning"
            : "tabular text-xs font-medium"
        }
      >
        {value}
      </span>
    </div>
  );
}

function TodaySessions() {
  const today = useToday();
  if (!today.data) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today&apos;s Sessions</CardTitle>
        <CardDescription>
          {today.data.sessions} session{today.data.sessions === 1 ? "" : "s"} on{" "}
          {formatDate(today.data.on_date)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {today.data.sessions === 0 ? (
          <EmptyState
            title="No sessions today"
            description="Nothing has been imported for today yet. This is not the same as nobody training — check the import status if you expected data."
          />
        ) : (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="tabular">
              {today.data.tracked_events.toLocaleString()} tracked events from{" "}
              {today.data.athletes_trained} athletes
            </span>
            <SourceStatusBadge status="PRELIMINARY" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
