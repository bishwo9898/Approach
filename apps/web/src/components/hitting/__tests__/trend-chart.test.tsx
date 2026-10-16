import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendChart } from "@/components/hitting/trend-chart";
import type { TrendBucket } from "@/lib/types";

/**
 * The rule most likely to regress silently: a bucket with no session must
 * break the line rather than be dropped or drawn as a zero. Dropping it
 * redraws the axis and makes an inconsistent athlete look consistent; a zero
 * claims a measurement that never happened.
 *
 * Asserted on the SVG itself, because that is where it actually happens.
 */

const full = (label: string, avg: number, best: number): TrendBucket => ({
  start: `2026-09-${label}`,
  end: `2026-09-${label}`,
  label,
  sessions: 1,
  pitches_faced: 20,
  batted_balls: 6,
  best_exit_velocity_mph: best,
  average_exit_velocity_mph: avg,
  sweet_spot_rate: 50,
});

const blank = (label: string): TrendBucket => ({
  start: `2026-09-${label}`,
  end: `2026-09-${label}`,
  label,
  sessions: 0,
  pitches_faced: 0,
  batted_balls: 0,
  best_exit_velocity_mph: null,
  average_exit_velocity_mph: null,
  sweet_spot_rate: null,
});

/** The "typical ball" line: solid, as opposed to the dashed "hardest ball". */
function averagePaths(container: HTMLElement): SVGPathElement[] {
  return Array.from(container.querySelectorAll("path")).filter(
    (p) => !p.getAttribute("stroke-dasharray"),
  ) as SVGPathElement[];
}

/**
 * SVG <title> carries the per-point detail. Read by tag rather than with
 * getByTitle, which in jsdom only matches the HTML title *attribute*.
 */
function titles(container: HTMLElement): string[] {
  return Array.from(container.getElementsByTagName("title")).map(
    (node) => node.textContent ?? "",
  );
}

function axisText(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("text")).map((n) => n.textContent ?? "");
}

describe("TrendChart", () => {
  it("draws one continuous line when every bucket has a session", () => {
    const { container } = render(
      <TrendChart
        buckets={[full("01", 80, 90), full("02", 82, 92), full("03", 84, 94)]}
        grainLabel="by day"
      />,
    );

    const paths = averagePaths(container);
    expect(paths).toHaveLength(1);
    // One "move to", so the line is drawn in a single unbroken run.
    expect(paths[0]?.getAttribute("d")?.match(/M /g) ?? []).toHaveLength(1);
  });

  it("breaks the line where a bucket has no session", () => {
    const { container } = render(
      <TrendChart
        buckets={[full("01", 80, 90), blank("02"), full("03", 84, 94)]}
        grainLabel="by day"
      />,
    );

    // Two separate runs, not one line interpolated across the gap.
    expect(averagePaths(container)).toHaveLength(2);
  });

  it("keeps the empty bucket, labelled, rather than dropping it", () => {
    const { container } = render(
      <TrendChart
        buckets={[full("01", 80, 90), blank("02"), full("03", 84, 94)]}
        grainLabel="by day"
      />,
    );

    expect(titles(container)).toContain("02: no session");
    // Its label stays on the axis, so the gap is visible rather than silent.
    expect(axisText(container)).toContain("02");
  });

  it("puts the sample size behind every plotted point", () => {
    const { container } = render(
      <TrendChart
        buckets={[full("01", 80, 90), full("02", 82, 92)]}
        grainLabel="by day"
      />,
    );

    expect(titles(container).some((t) => t.includes("6 batted balls in 1 session"))).toBe(
      true,
    );
  });

  it("renders nothing when no bucket was ever measured", () => {
    const { container } = render(
      <TrendChart buckets={[blank("01"), blank("02")]} grainLabel="by day" />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("does not anchor the scale at zero, which would flatten real differences", () => {
    const { container } = render(
      <TrendChart
        buckets={[full("01", 80, 90), full("02", 82, 92)]}
        grainLabel="by day"
      />,
    );

    // The axis brackets the data (80-92) rather than starting at zero, which
    // would squash every real difference into the top eighth of the chart.
    const ticks = axisText(container)
      .map(Number)
      .filter((n) => !Number.isNaN(n) && n > 50);
    expect(Math.min(...ticks)).toBeGreaterThan(50);
    expect(Math.min(...ticks)).toBeLessThan(80);
    expect(Math.max(...ticks)).toBeGreaterThan(92);
  });
});
