"use client";

import { Button } from "@/components/ui/button";
import { TIME_RANGE_LABELS } from "@/lib/format";
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
    <div className="flex flex-wrap gap-1" role="group" aria-label="Time range">
      {RANGES.map((range) => (
        <Button
          key={range}
          size="sm"
          variant={range === value ? "default" : "outline"}
          aria-pressed={range === value}
          onClick={() => onChange(range)}
        >
          {TIME_RANGE_LABELS[range]}
        </Button>
      ))}
    </div>
  );
}
