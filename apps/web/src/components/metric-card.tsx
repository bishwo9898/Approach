"use client";

import { Card, CardContent } from "@/components/ui/card";
import { SourceStatusBadge } from "@/components/source-status-badge";
import {
  changeTone,
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
 * One headline metric: what it is now, how it moved, and the standing record.
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

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              {definition.display_name}
            </p>
            <p className="tabular mt-1 text-2xl font-semibold tracking-tight">
              {formatMeasurement(latest.value, definition.unit, precision)}
            </p>
          </div>
          <SourceStatusBadge status={latest.source_status} />
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

        <div className="flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
          <span className="tabular">
            {latest.sample_size > 0 ? formatSample(latest.sample_size) : "no samples"}
          </span>
          {record ? (
            <span className="tabular">
              PR{" "}
              <strong className="font-semibold text-foreground">
                {formatMeasurement(record.value, record.unit, record.display_precision)}
              </strong>
            </span>
          ) : (
            <span>No record yet</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
