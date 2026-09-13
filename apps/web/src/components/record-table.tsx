"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { SourceStatusBadge } from "@/components/source-status-badge";
import { formatDate, formatMeasurement, formatSample } from "@/lib/format";
import type { PersonalRecord } from "@/lib/types";

export function RecordTable({ records }: { records: PersonalRecord[] }) {
  if (records.length === 0) {
    return (
      <EmptyState
        title="No personal records yet"
        description="A record needs enough tracked events to be credible — see each metric's minimum sample size."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="py-2 pr-4 font-medium">Metric</th>
            <th className="py-2 pr-4 text-right font-medium">Record</th>
            <th className="py-2 pr-4 font-medium">Achieved</th>
            <th className="py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {records.map((record) => (
            <tr key={record.metric_key}>
              <td className="py-2.5 pr-4 font-medium">{record.metric_display_name}</td>
              <td className="tabular py-2.5 pr-4 text-right font-semibold">
                {formatMeasurement(record.value, record.unit, record.display_precision)}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {formatSample(record.sample_size)}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-muted-foreground">
                {formatDate(record.achieved_on)}
              </td>
              <td className="flex items-center gap-1 py-2.5">
                <SourceStatusBadge status={record.source_status} />
                {record.is_manual_override ? (
                  <Badge
                    variant="outline"
                    title="Set by an administrator, not by the engine."
                  >
                    Manual
                  </Badge>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
