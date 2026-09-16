"use client";

import { TIME_RANGE_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TimeRange } from "@/lib/types";

const RANGES: TimeRange[] = ["today", "7d", "30d", "90d", "1y", "all"];

export function TimeRangePicker({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}) {
  return (
    <div
      className="flex flex-wrap gap-1 rounded-xl border border-border/80 bg-card p-1 shadow-sm"
      role="group"
      aria-label="Time range"
    >
      {RANGES.map((range) => (
        <button
          key={range}
          aria-pressed={range === value}
          onClick={() => onChange(range)}
          className={cn(
            "rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            range === value
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {TIME_RANGE_LABELS[range]}
        </button>
      ))}
    </div>
  );
}
