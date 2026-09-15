"use client";

import { Card, CardContent } from "@/components/ui/card";
import { SourceStatusBadge } from "@/components/source-status-badge";
import {
  changeTone,
  formatDate,
  formatDelta,
  formatMeasurement,
  formatSample,
  TIME_RANGE_LABELS,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MetricSummary, TimeRange } from "@/lib/types";

const TONE_CLASS = {
  positive: "text-positive",
  negative: "text-negative",
  neutral: "text-muted-foreground",
} as const;

/**
 * One headline metric: its selected-period result, movement, latest session,
 * and standing record.
 *
 * Every number carries its unit and its sample size. An average off three
 * pitches and an average off forty are not the same claim, and the card never
 * lets them look alike.
 */
export function MetricCard({
  summary,
  range,
}: {
  summary: MetricSummary;
  range: TimeRange;
}) {
  const { definition, latest, window, record } = summary;
  const precision = definition.display_precision;
  const tone = changeTone(window.delta, definition.record_direction);
  const delta = formatDelta(window.delta, precision);
  const periodLabel = TIME_RANGE_LABELS[range] ?? range;

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div>
          <p className="text-xs font-medium text-muted-foreground">
            {definition.display_name}
          </p>
          <p className="tabular mt-1 text-2xl font-semibold tracking-tight">
            {formatMeasurement(window.current, definition.unit, precision)}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{periodLabel}</span>
            <span aria-hidden="true">·</span>
            <span className="tabular">
              {window.current_sample > 0
                ? formatSample(window.current_sample)
                : "no samples"}
            </span>
            <SourceStatusBadge status={window.current_source_status} />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          {delta ? (
            <span className={cn("tabular font-medium", TONE_CLASS[tone])}>
              {delta} {definition.unit !== "count" ? definition.unit : ""}
            </span>
          ) : (
            <span className="text-muted-foreground">No prior period</span>
          )}
          <span className="text-muted-foreground">
            vs previous {TIME_RANGE_LABELS[range]?.toLowerCase() ?? range}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 border-t border-border pt-3 text-xs">
          <div>
            <p className="text-muted-foreground">Latest session</p>
            <p className="tabular mt-0.5 font-medium text-foreground">
              {formatMeasurement(latest.value, definition.unit, precision)}
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {latest.observed_on ? formatDate(latest.observed_on) : "No session yet"}
            </p>
          </div>
          <div className="text-right">
            <p className="text-muted-foreground">Personal record</p>
            {record ? (
              <>
                <p className="tabular mt-0.5 font-semibold text-foreground">
                  {formatMeasurement(record.value, record.unit, record.display_precision)}
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {formatDate(record.achieved_on)}
                </p>
              </>
            ) : (
              <p className="mt-0.5 text-muted-foreground">Not tracked as a PR</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
