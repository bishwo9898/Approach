"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useMemo, useState } from "react";

import { MetricCard } from "@/components/metric-card";
import { ProgressionChart } from "@/components/progression-chart";
import { RecordTable } from "@/components/record-table";
import { SessionTable } from "@/components/session-table";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { TimeRangePicker } from "@/components/time-range-picker";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon } from "@/components/ui/icons";
import {
  usePlayerOverview,
  usePlayerRecords,
  usePlayerSeries,
  usePlayerSessions,
} from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import type { TimeRange } from "@/lib/types";

type Tab = "overview" | "prs" | "sessions";

export default function CoachPlayerPage() {
  const params = useParams<{ playerId: string }>();
  const playerId = params.playerId;

  const [range, setRange] = useState<TimeRange>("30d");
  const [tab, setTab] = useState<Tab>("overview");

  const overview = usePlayerOverview(playerId, range);
  const records = usePlayerRecords(playerId);
  const sessions = usePlayerSessions(playerId, 25);

  // Default the chart to the athlete's first headline metric -- for a pitcher
  // that is fastball velocity, for a hitter exit velocity, without the page
  // needing to know which is which.
  const [metricKey, setMetricKey] = useState<string | undefined>(undefined);
  const activeMetricKey = metricKey ?? overview.data?.metrics[0]?.definition.key;
  const series = usePlayerSeries(playerId, activeMetricKey, range);

  const recordForChart = useMemo(
    () =>
      overview.data?.metrics.find((m) => m.definition.key === activeMetricKey)?.record
        ?.value ?? null,
    [overview.data, activeMetricKey],
  );

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
        title="This athlete is not available"
        description="They may not exist, or you may not have access to them."
      />
    );
  }

  const {
    player,
    last_session: lastSession,
    sessions_in_window: sessionsInWindow,
  } = overview.data;

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-[1.2rem] border border-border/80 bg-card shadow-[0_8px_30px_rgba(15,23,42,0.05)]">
        <div className="h-1.5 bg-gradient-to-r from-blue-600 via-blue-400 to-cyan-300" />
        <div className="flex flex-wrap items-end justify-between gap-6 p-6 sm:p-7">
          <div>
            <Link
              href="/coach/players"
              className="mb-4 inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground"
            >
              <Icon name="arrow" className="size-3 rotate-180" /> Back to roster
            </Link>
            <div className="flex items-center gap-4">
              <span className="grid size-14 place-items-center rounded-2xl bg-primary text-base font-semibold text-primary-foreground shadow-md">
                {player.display_name
                  .split(" ")
                  .map((part) => part[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-foreground">
                  Athlete profile
                </p>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">
                  {player.display_name}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[
                    player.position,
                    player.graduation_year ? `Class of ${player.graduation_year}` : null,
                    player.bats ? `B/T ${player.bats}/${player.throws ?? "—"}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
          </div>
          <TimeRangePicker value={range} onChange={setRange} />
        </div>
        <div className="grid border-t border-border/80 bg-muted/25 sm:grid-cols-4 sm:divide-x sm:divide-border/80">
          <div>
            <div className="px-5 py-4">
              <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Last session
              </p>
              <p className="mt-1 text-sm font-semibold">
                {lastSession ? formatDate(lastSession.session_date) : "No sessions yet"}
              </p>
            </div>
          </div>
          {lastSession ? (
            <>
              <div>
                <div className="px-5 py-4">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Tracked events
                  </p>
                  <p className="tabular mt-1 text-sm font-semibold">
                    {lastSession.pitch_count + lastSession.hit_count}
                  </p>
                </div>
              </div>
              <div>
                <div className="px-5 py-4">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    Data status
                  </p>
                  <div className="mt-1">
                    <SourceStatusBadge status={lastSession.source_status} />
                  </div>
                </div>
              </div>
            </>
          ) : null}
          <div>
            <div className="px-5 py-4">
              <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Sessions in range
              </p>
              <p className="tabular mt-1 text-sm font-semibold">{sessionsInWindow}</p>
            </div>
          </div>
        </div>
      </section>

      <nav
        className="flex w-fit gap-1 rounded-xl border border-border bg-card p-1 shadow-sm"
        role="tablist"
      >
        {(["overview", "prs", "sessions"] as const).map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={
              tab === value
                ? "rounded-lg bg-primary px-3.5 py-2 text-xs font-medium text-primary-foreground shadow-sm"
                : "rounded-lg px-3.5 py-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            }
          >
            {value === "prs"
              ? "Personal Records"
              : value[0]!.toUpperCase() + value.slice(1)}
          </button>
        ))}
      </nav>

      {tab === "overview" ? (
        <div className="space-y-6">
          <section className="space-y-3" aria-labelledby="performance-snapshot">
            <div>
              <h2
                id="performance-snapshot"
                className="text-lg font-semibold tracking-tight"
              >
                Performance snapshot
              </h2>
              <p className="text-sm text-muted-foreground">
                High, average, and low values for the selected period.
              </p>
            </div>
            {overview.data.metrics.length === 0 ? (
              <EmptyState
                title="No tracked metrics for this athlete"
                description="Nothing has been imported for them yet, or their sessions did not meet any metric's minimum sample size."
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {overview.data.metrics.map((summary) => (
                  <MetricCard
                    key={summary.definition.key}
                    summary={summary}
                    range={range}
                  />
                ))}
              </div>
            )}
          </section>

          <Card>
            <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
              <div>
                <CardTitle>Progression</CardTitle>
                <CardDescription>
                  Session-by-session, dashed line is the record
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-1">
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
                <Skeleton className="h-[260px] w-full" />
              ) : series.data ? (
                <ProgressionChart
                  definition={series.data.definition}
                  points={series.data.points}
                  recordValue={recordForChart}
                />
              ) : (
                <EmptyState title="No progression data" />
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === "prs" ? (
        <Card>
          <CardHeader>
            <CardTitle>Personal records</CardTitle>
            <CardDescription>All time, across every tracked metric</CardDescription>
          </CardHeader>
          <CardContent>
            {records.isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <RecordTable records={records.data ?? []} />
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "sessions" ? (
        <Card>
          <CardHeader>
            <CardTitle>Session history</CardTitle>
            <CardDescription>Most recent first</CardDescription>
          </CardHeader>
          <CardContent>
            {sessions.isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <SessionTable sessions={sessions.data ?? []} />
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
