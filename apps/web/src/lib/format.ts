/**
 * Display formatting.
 *
 * Two rules the whole UI depends on:
 *   1. A measurement is never rendered without its unit.
 *   2. A change is never rendered without its direction being meaningful --
 *      which requires knowing whether higher or lower is better for that metric.
 */

import type { RecordDirection } from "@/lib/types";

/** Render a measurement with its unit, at the metric's declared precision. */
export function formatMeasurement(
  value: number | null | undefined,
  unit: string,
  precision = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rendered = value.toFixed(precision);
  if (unit === "%") return `${rendered}%`;
  if (unit === "count") return rendered;
  return `${rendered} ${unit}`;
}

/** A signed change, e.g. "+2.4" or "−0.7". Sign is always explicit. */
export function formatDelta(
  delta: number | null | undefined,
  precision = 1,
): string | null {
  if (delta === null || delta === undefined || Number.isNaN(delta)) return null;
  if (Math.abs(delta) < 10 ** -precision / 2) return "no change";
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${Math.abs(delta).toFixed(precision)}`;
}

export type ChangeTone = "positive" | "negative" | "neutral";

/**
 * Whether a change is an improvement.
 *
 * A drop in velocity is shown as a drop in velocity. This function decides
 * colour, not meaning -- nothing in this application infers injury, risk, or
 * anything medical from a change in a number.
 */
export function changeTone(
  delta: number | null | undefined,
  direction: RecordDirection,
): ChangeTone {
  if (delta === null || delta === undefined || delta === 0) return "neutral";
  if (direction === "NONE") return "neutral";
  const improving = direction === "HIGHER_IS_BETTER" ? delta > 0 : delta < 0;
  return improving ? "positive" : "negative";
}

/** "Sep 12, 2026" from an ISO date, without timezone drift. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "—";
  // Constructed in UTC and read back in UTC: a plain calendar date must not be
  // shifted a day by the viewer's timezone.
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "3 days ago" -- for operational freshness, where exactness is not the point. */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "never";
  const seconds = Math.floor((Date.now() - parsed.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** "n = 24" -- always shown next to an aggregate so it cannot mislead. */
export function formatSample(sampleSize: number): string {
  return `n=${sampleSize}`;
}

export const TIME_RANGE_LABELS: Record<string, string> = {
  today: "Today",
  "7d": "7 Days",
  "30d": "30 Days",
  "90d": "90 Days",
  "1y": "Year",
  all: "All Time",
};
