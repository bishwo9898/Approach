"use client";

import { useState } from "react";

import { MetricCard } from "@/components/metric-card";
import { ProgressionChart } from "@/components/progression-chart";
import { RecordTable } from "@/components/record-table";
import { SessionTable } from "@/components/session-table";
import { TimeRangePicker } from "@/components/time-range-picker";
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
import {
  useCurrentUser,
  useMyOverview,
  useMyRecords,
  useMySessions,
  usePlayerSeries,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import type { TimeRange } from "@/lib/types";

/**
 * The athlete's own dashboard.
 *
 * Every request here is scoped to the caller by the server (`/api/v1/me/*`), so
 * this page never sends an athlete id and there is no id to tamper with.
 */
export default function PlayerDashboard() {
  const [range, setRange] = useState<TimeRange>("30d");
  const user = useCurrentUser();
  const overview = useMyOverview(range);
  const records = useMyRecords();
  const sessions = useMySessions(10);

  const primaryKey = overview.data?.metrics[0]?.definition.key;
  const series = usePlayerSeries(user.data?.player_id ?? "", primaryKey, range);

  if (overview.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (overview.isError || !overview.data) {
    return (
      <EmptyState
        title="No athlete profile linked to this account"
        description="Ask a coach to link your login to your athlete record."
      />
    );
  }

  const firstName =
    overview.data.player.preferred_name ?? overview.data.player.first_name;
  const lastSession = overview.data.last_session;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome, {firstName}</h1>
          <p className="text-sm text-muted-foreground">
            {lastSession
              ? `Last training session ${formatDate(lastSession.session_date)}`
              : "No training sessions recorded yet"}
          </p>
        </div>
        <TimeRangePicker value={range} onChange={setRange} />
      </header>

      {lastSession ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-6 p-5 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Tracked events</p>
              <p className="tabular font-medium">
                {lastSession.pitch_count + lastSession.hit_count}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sessions in range</p>
              <p className="tabular font-medium">{overview.data.sessions_in_window}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Data status</p>
              <SourceStatusBadge status={lastSession.source_status} />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {overview.data.metrics.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {overview.data.metrics.map((summary) => (
            <MetricCard key={summary.definition.key} summary={summary} range={range} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No metrics yet"
          description="Your numbers appear here once a tracked session is imported."
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Your Progression</CardTitle>
          <CardDescription>
            {series.data?.definition.display_name ?? "Session by session"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {series.isLoading ? (
            <Skeleton className="h-[260px] w-full" />
          ) : series.data ? (
            <ProgressionChart
              definition={series.data.definition}
              points={series.data.points}
              recordValue={overview.data.metrics[0]?.record?.value ?? null}
            />
          ) : (
            <EmptyState title="No progression data yet" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Your Personal Records</CardTitle>
          </CardHeader>
          <CardContent>
            {records.isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <RecordTable records={records.data ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            {sessions.isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <SessionTable sessions={sessions.data ?? []} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
