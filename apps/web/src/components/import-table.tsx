"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useImportDetail, useReprocessImport } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/format";
import type { ImportSummary } from "@/lib/types";

const STATUS_VARIANT: Record<string, "positive" | "warning" | "negative" | "default"> = {
  SUCCESS: "positive",
  PARTIAL: "warning",
  FAILED: "negative",
  SKIPPED_DUPLICATE: "default",
  RECEIVED: "default",
  PROCESSING: "default",
};

/**
 * Import history, with the rejected rows one click away.
 *
 * A failed or partial import that is not visible is worse than one that never
 * ran: the dashboard keeps rendering and the coach reads stale numbers as
 * current.
 */
export function ImportTable({ imports }: { imports: ImportSummary[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (imports.length === 0) {
    return (
      <EmptyState
        title="No imports yet"
        description="Upload a TrackMan export above to get started."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="py-2 pr-4 font-medium">When</th>
            <th className="py-2 pr-4 font-medium">File</th>
            <th className="py-2 pr-4 text-right font-medium">Rows</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {imports.map((item) => (
            <ImportRow
              key={item.id}
              item={item}
              expanded={expanded === item.id}
              onToggle={() => setExpanded(expanded === item.id ? null : item.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ImportRow({
  item,
  expanded,
  onToggle,
}: {
  item: ImportSummary;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detail = useImportDetail(expanded ? item.id : null);
  const reprocess = useReprocessImport();
  // `issues` is optional in the API contract (it defaults to an empty list),
  // so normalize once rather than guarding at each use.
  const issues = detail.data?.issues ?? [];
  const hasProblems = item.rows_rejected > 0 || item.status === "FAILED";

  return (
    <>
      <tr>
        <td className="py-2.5 pr-4 text-muted-foreground">
          {formatDateTime(item.created_at)}
        </td>
        <td className="max-w-[220px] truncate py-2.5 pr-4 font-medium">
          {item.filename ?? "—"}
        </td>
        <td className="tabular py-2.5 pr-4 text-right">
          {item.rows_accepted}/{item.rows_total}
          {item.rows_rejected > 0 ? (
            <span className="ml-1 text-warning">(−{item.rows_rejected})</span>
          ) : null}
        </td>
        <td className="py-2.5 pr-4">
          <Badge variant={STATUS_VARIANT[item.status] ?? "default"}>
            {item.status.replace("_", " ").toLowerCase()}
          </Badge>
        </td>
        <td className="py-2.5 text-right">
          <div className="flex justify-end gap-1">
            {hasProblems ? (
              <Button size="sm" variant="ghost" onClick={onToggle}>
                {expanded ? "Hide" : "Issues"}
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              disabled={reprocess.isPending || !item.rows_total}
              title="Re-run this import from its archived source file"
              onClick={() => reprocess.mutate(item.id)}
            >
              Reprocess
            </Button>
          </div>
        </td>
      </tr>

      {expanded ? (
        <tr>
          <td colSpan={5} className="bg-muted/30 px-4 py-3">
            {item.error_message ? (
              <p className="mb-2 text-xs text-negative">{item.error_message}</p>
            ) : null}
            {detail.isLoading ? (
              <p className="text-xs text-muted-foreground">Loading issues…</p>
            ) : issues.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No row-level issues recorded.
              </p>
            ) : (
              <ul className="space-y-1">
                {issues.slice(0, 25).map((issue, index) => (
                  <li key={index} className="text-xs">
                    <span className="tabular text-muted-foreground">
                      {issue.row_number ? `row ${issue.row_number}` : "file"}
                    </span>{" "}
                    <span className="font-medium">{issue.code}</span>{" "}
                    <span className="text-muted-foreground">{issue.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      ) : null}
    </>
  );
}
