"use client";

import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { PlayerSearch } from "@/components/player-search";
import { RecordFeed } from "@/components/record-feed";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { StatTile } from "@/components/stat-tile";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntegrationStatus, useRecentRecords, useToday } from "@/hooks/use-api";
import { formatDate, formatRelative } from "@/lib/format";

/** The coach's home: today's activity, new records, and search. */
export default function CoachDashboard() {
  const today = useToday();
  const records = useRecentRecords(14, 12);
  const health = useIntegrationStatus();

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Coach workspace"
        title="Training overview"
        description="A clear view of today’s activity, athlete milestones, and the data that powers your decisions."
        action={
          <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card px-3.5 py-2.5 text-xs font-medium text-muted-foreground shadow-sm">
            <Icon name="sessions" className="size-4 text-accent-foreground" />
            {today.data ? formatDate(today.data.on_date) : "Loading today…"}
          </div>
        }
      />

      <section aria-label="Today's activity" className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Today at a glance</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Live from imported TrackMan sessions
            </p>
          </div>
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-positive">
            <span className="size-1.5 rounded-full bg-positive" />
            Monitoring active
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {today.isLoading || !today.data ? (
            Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-[112px]" />
            ))
          ) : (
            <>
              <StatTile
                label="Athletes trained"
                value={today.data.athletes_trained}
                icon="players"
                tone="blue"
                hint="Unique athletes today"
              />
              <StatTile
                label="Sessions"
                value={today.data.sessions}
                icon="sessions"
                tone="violet"
                hint="Imported training sessions"
              />
              <StatTile
                label="Tracked events"
                value={today.data.tracked_events.toLocaleString()}
                icon="activity"
                tone="green"
                hint="Pitches and batted balls"
              />
              <StatTile
                label="New personal records"
                value={today.data.new_personal_records}
                icon="trophy"
                tone="amber"
                hint="Milestones worth celebrating"
              />
            </>
          )}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
            <div>
              <CardTitle>Recent personal records</CardTitle>
              <CardDescription>
                New milestones across the roster in the last 14 days
              </CardDescription>
            </div>
            <span className="grid size-9 place-items-center rounded-xl bg-amber-50 text-amber-600">
              <Icon name="trophy" className="size-4" />
            </span>
          </CardHeader>
          <CardContent>
            {records.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }, (_, index) => (
                  <Skeleton key={index} className="h-14 w-full" />
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
              <CardTitle className="flex items-center gap-2">
                <Icon name="search" className="size-4 text-accent-foreground" /> Find an
                athlete
              </CardTitle>
              <CardDescription>
                Open a profile to review progress and recent sessions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PlayerSearch />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
              <div>
                <CardTitle>Data health</CardTitle>
                <CardDescription>
                  Pipeline status and items needing attention
                </CardDescription>
              </div>
              <Link
                href="/coach/operations"
                className="group flex items-center gap-1 text-xs font-medium text-accent-foreground hover:underline"
              >
                View details{" "}
                <Icon
                  name="arrow"
                  className="size-3 transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {health.isLoading || !health.data ? (
                <Skeleton className="h-32 w-full" />
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
    <div className="flex items-center justify-between rounded-lg px-2 py-2.5 transition-colors hover:bg-muted/50">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={
          alert
            ? "tabular rounded-full bg-amber-50 px-2 py-1 text-[11px] font-semibold text-warning"
            : "tabular text-xs font-semibold"
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
        <CardTitle>Today’s sessions</CardTitle>
        <CardDescription>
          {today.data.sessions} session{today.data.sessions === 1 ? "" : "s"} on{" "}
          {formatDate(today.data.on_date)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {today.data.sessions === 0 ? (
          <EmptyState
            title="No sessions imported today"
            description="If athletes have already trained, check Data Health to confirm that the latest TrackMan export was received."
          />
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-xl bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
            <span className="grid size-8 place-items-center rounded-lg bg-card text-accent-foreground shadow-sm">
              <Icon name="activity" className="size-4" />
            </span>
            <span className="tabular font-medium text-foreground">
              {today.data.tracked_events.toLocaleString()} tracked events
            </span>
            <span>from {today.data.athletes_trained} athletes</span>
            <span className="ml-auto">
              <SourceStatusBadge status="PRELIMINARY" />
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
