"use client";

import { useMemo, useState } from "react";

import { MetricCard } from "@/components/metric-card";
import { ProgressionChart } from "@/components/progression-chart";
import { RecordTable } from "@/components/record-table";
import { SessionTable } from "@/components/session-table";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { TimeRangePicker } from "@/components/time-range-picker";
import { Button } from "@/components/ui/button";
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
import {
  useCurrentUser,
  useMyOverview,
  useMyRecords,
  useMySessions,
  usePlayerSeries,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import type { TimeRange } from "@/lib/types";

/** The athlete's server-scoped performance dashboard. */
export default function PlayerDashboard() {
  const [range, setRange] = useState<TimeRange>("30d");
  const [metricKey, setMetricKey] = useState<string>();
  const user = useCurrentUser();
  const overview = useMyOverview(range);
  const records = useMyRecords();
  const sessions = useMySessions(10);
  const activeMetricKey = metricKey ?? overview.data?.metrics[0]?.definition.key;
  const series = usePlayerSeries(user.data?.player_id ?? "", activeMetricKey, range);
  const recordForChart = useMemo(
    () =>
      overview.data?.metrics.find((metric) => metric.definition.key === activeMetricKey)
        ?.record?.value ?? null,
    [activeMetricKey, overview.data],
  );

  if (overview.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-48 w-full" />
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

  const { player, last_session: lastSession } = overview.data;
  const firstName = player.preferred_name ?? player.first_name;
  const initials = player.display_name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("");

  return (
    <div className="space-y-8">
      <section className="surface-grid relative overflow-hidden rounded-[1.35rem] bg-[#0b1730] p-6 text-white shadow-[0_18px_50px_rgba(11,23,48,0.18)] sm:p-8">
        <div className="absolute -right-16 -top-20 size-64 rounded-full bg-blue-500/15 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="flex items-center gap-4">
            <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-white/10 text-xl font-semibold text-blue-100 ring-1 ring-white/15">
              {initials}
            </span>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-300">
                My performance
              </p>
              <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
                Welcome back, {firstName}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                {lastSession
                  ? `Latest session · ${formatDate(lastSession.session_date)}`
                  : "Your first tracked session will appear here."}
              </p>
            </div>
          </div>
          <div className="rounded-xl bg-white p-1 text-foreground shadow-lg">
            <TimeRangePicker value={range} onChange={setRange} />
          </div>
        </div>

        <div className="relative mt-7 grid gap-px overflow-hidden rounded-xl bg-white/10 sm:grid-cols-3">
          <HeroMetric
            label="Sessions in range"
            value={String(overview.data.sessions_in_window)}
            icon="sessions"
          />
          <HeroMetric
            label="Latest tracked events"
            value={
              lastSession ? String(lastSession.pitch_count + lastSession.hit_count) : "—"
            }
            icon="activity"
          />
          <div className="flex items-center gap-3 bg-white/[0.055] px-4 py-3.5">
            <span className="grid size-8 place-items-center rounded-lg bg-white/10 text-blue-200">
              <Icon name="check" className="size-4" />
            </span>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-400">
                Data status
              </p>
              <div className="mt-1">
                {lastSession ? (
                  <SourceStatusBadge status={lastSession.source_status} />
                ) : (
                  <span className="text-sm font-medium">No data yet</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4" aria-labelledby="performance-snapshot">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2
              id="performance-snapshot"
              className="text-lg font-semibold tracking-tight"
            >
              Performance snapshot
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Your key metrics, current trend, and all-time best for this period.
            </p>
          </div>
          <span className="hidden text-xs text-muted-foreground sm:block">
            {overview.data.metrics.length} metrics tracked
          </span>
        </div>
        {overview.data.metrics.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
      </section>

      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle>Your progression</CardTitle>
            <CardDescription>
              Follow your session-by-session trend; the dashed line marks your record
            </CardDescription>
          </div>
          <div className="flex max-w-full flex-wrap gap-1.5">
            {overview.data.metrics.map((summary) => (
              <Button
                key={summary.definition.key}
                size="sm"
                variant={
                  summary.definition.key === activeMetricKey ? "default" : "outline"
                }
                onClick={() => setMetricKey(summary.definition.key)}
              >
                {summary.definition.display_name}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {series.isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : series.data ? (
            <ProgressionChart
              definition={series.data.definition}
              points={series.data.points}
              recordValue={recordForChart}
            />
          ) : (
            <EmptyState title="No progression data yet" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <span className="grid size-9 place-items-center rounded-xl bg-amber-50 text-amber-600">
              <Icon name="trophy" className="size-4" />
            </span>
            <div>
              <CardTitle>Personal records</CardTitle>
              <CardDescription>Your all-time benchmarks</CardDescription>
            </div>
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
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-600">
              <Icon name="sessions" className="size-4" />
            </span>
            <div>
              <CardTitle>Recent sessions</CardTitle>
              <CardDescription>Your latest tracked training</CardDescription>
            </div>
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

function HeroMetric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: "sessions" | "activity";
}) {
  return (
    <div className="flex items-center gap-3 bg-white/[0.055] px-4 py-3.5">
      <span className="grid size-8 place-items-center rounded-lg bg-white/10 text-blue-200">
        <Icon name={icon} className="size-4" />
      </span>
      <div>
        <p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p>
        <p className="tabular mt-0.5 text-lg font-semibold">{value}</p>
      </div>
    </div>
  );
}
