"use client";

import { Button } from "@/components/ui/button";
import type { TimeRange } from "@/lib/types";

/** What the athlete's page can be looked at as. */
export type View = "session" | TimeRange;

/**
 * The one control for the whole feature.
 *
 * It picks a window; how the window is cut up for the trend follows from its
 * length and is decided on the server. There is no second control, so there is
 * no combination to get wrong -- thirty daily points is mostly empty space for
 * someone who trains twice a week, and twelve monthly points says nothing about
 * the last fortnight.
 *
 * "Today" and "This year" are deliberately absent: today is almost always empty
 * and a year of buckets is unreadable until there are years of data. They stay
 * available on the API.
 */
const OPTIONS: { view: View; label: string; title: string }[] = [
  { view: "session", label: "Last session", title: "The most recent session on its own" },
  { view: "7d", label: "Week", title: "The last 7 days, by day" },
  { view: "30d", label: "Month", title: "The last 30 days, by week" },
  { view: "90d", label: "Quarter", title: "The last 90 days, by week" },
  { view: "all", label: "All time", title: "Every session, by month" },
];

export function PeriodPicker({
  value,
  onChange,
}: {
  value: View;
  onChange: (view: View) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Period">
      {OPTIONS.map((option) => (
        <Button
          key={option.view}
          size="sm"
          variant={option.view === value ? "default" : "outline"}
          title={option.title}
          aria-pressed={option.view === value}
          onClick={() => onChange(option.view)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
