"use client";

import type { Insight } from "@/lib/types";

const STYLES = {
  STRENGTH: {
    label: "Strength",
    box: "border-positive/25 bg-positive/5",
    chip: "bg-positive/15 text-positive",
  },
  WORK_ON: {
    label: "Work on",
    box: "border-warning/25 bg-warning/5",
    chip: "bg-warning/15 text-warning",
  },
  NOTE: {
    label: "Keep in mind",
    box: "border-border bg-muted/40",
    chip: "bg-muted text-muted-foreground",
  },
} as const;

const ORDER = { STRENGTH: 0, WORK_ON: 1, NOTE: 2 } as const;

/**
 * What a coach would say about the session.
 *
 * Notes come last and look quieter on purpose -- they are the sample-size
 * caveats, and they should be read after the finding they qualify rather than
 * competing with it.
 */
export function InsightList({ insights }: { insights: Insight[] }) {
  const sorted = [...insights].sort(
    (a, b) =>
      (ORDER[a.kind as keyof typeof ORDER] ?? 3) -
      (ORDER[b.kind as keyof typeof ORDER] ?? 3),
  );

  return (
    <ul className="space-y-2">
      {sorted.map((insight, index) => {
        const style = STYLES[insight.kind as keyof typeof STYLES] ?? STYLES.NOTE;
        return (
          <li key={index} className={`rounded-lg border p-4 ${style.box}`}>
            <span
              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${style.chip}`}
            >
              {style.label}
            </span>
            <p className="mt-2 text-sm font-semibold leading-snug">{insight.headline}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {insight.detail}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
