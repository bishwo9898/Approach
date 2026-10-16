import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HittingPeriodView } from "@/components/hitting/period-summary";
import type { HittingPeriodSummary, TrendBucket } from "@/lib/types";

/**
 * What this view must never do is imply more than was measured. These pin the
 * three ways it could: inventing a zero, drawing a trend through one point,
 * and showing a change against a period that does not exist.
 */

const bucket = (over: Partial<TrendBucket> = {}): TrendBucket => ({
  start: "2026-09-01",
  end: "2026-09-06",
  label: "Sep 1",
  sessions: 1,
  pitches_faced: 20,
  batted_balls: 6,
  best_exit_velocity_mph: 92,
  average_exit_velocity_mph: 84,
  sweet_spot_rate: 50,
  ...over,
});

const summary = (over: Partial<HittingPeriodSummary> = {}): HittingPeriodSummary =>
  ({
    player: {
      id: "p1",
      display_name: "Jordan Avery",
      first_name: "Jordan",
      last_name: "Avery",
      position: null,
      graduation_year: null,
      bats: null,
      throws: null,
    },
    range: "30d",
    start: "2026-09-01",
    end: "2026-09-30",
    grain: "week",
    grain_label: "by week",
    sessions: 2,
    first_session: "2026-09-02",
    last_session: "2026-09-16",
    has_data: true,
    has_trend: true,
    pitches_faced: 40,
    swings: 30,
    whiffs: 9,
    whiff_rate: 30,
    batted_balls: 12,
    best_exit_velocity_mph: 95,
    average_exit_velocity_mph: 84.2,
    sweet_spot_count: 7,
    sweet_spot_rate: 58.3,
    best_exit_velocity_change: {
      current: 95,
      previous: 91,
      delta: 4,
      percent_change: 4.4,
      current_sample: 12,
      previous_sample: 8,
    },
    average_exit_velocity_change: {
      current: 84.2,
      previous: 85.1,
      delta: -0.9,
      percent_change: -1.06,
      current_sample: 12,
      previous_sample: 8,
    },
    buckets: [bucket(), bucket({ start: "2026-09-08", label: "Sep 8" })],
    ...over,
  }) as HittingPeriodSummary;

describe("an empty period", () => {
  it("says there is nothing rather than showing zeros", () => {
    render(<HittingPeriodView summary={summary({ has_data: false, sessions: 0 })} />);

    expect(screen.getByText("Nothing to show yet")).toBeInTheDocument();
    expect(screen.queryByText("Hardest ball")).not.toBeInTheDocument();
  });

  it("still names the period it looked at", () => {
    render(<HittingPeriodView summary={summary({ has_data: false, sessions: 0 })} />);
    expect(screen.getByText(/Sep 1, 2026/)).toBeInTheDocument();
  });
});

describe("a period with one session", () => {
  const single = summary({
    sessions: 1,
    has_trend: false,
    first_session: "2026-09-02",
    last_session: "2026-09-02",
  });

  it("shows the numbers it does have", () => {
    render(<HittingPeriodView summary={single} />);
    expect(screen.getByText("1 session")).toBeInTheDocument();
    expect(screen.getByText("95.0")).toBeInTheDocument();
  });

  it("refuses to draw a trend through a single point", () => {
    render(<HittingPeriodView summary={single} />);

    expect(screen.getByText("Not enough for a trend yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("says the view fills in by itself, so it reads as early rather than broken", () => {
    render(<HittingPeriodView summary={single} />);
    expect(screen.getByText(/fills in on its own/)).toBeInTheDocument();
  });
});

describe("a period with a trend", () => {
  it("draws the chart", () => {
    render(<HittingPeriodView summary={summary()} />);
    expect(
      screen.getByRole("img", { name: /Exit velocity by week/ }),
    ).toBeInTheDocument();
  });

  it("reports the span of real sessions, not the window edges", () => {
    render(<HittingPeriodView summary={summary()} />);
    expect(screen.getByText(/Sep 2, 2026 – Sep 16, 2026/)).toBeInTheDocument();
  });

  it("attaches the sample size to every headline", () => {
    render(<HittingPeriodView summary={summary()} />);
    expect(screen.getByText(/across 12 batted balls/)).toBeInTheDocument();
    expect(screen.getByText(/7 of 12 balls/)).toBeInTheDocument();
    expect(screen.getByText(/9 of 30 swings/)).toBeInTheDocument();
  });
});

describe("change against the previous period", () => {
  it("shows a gain with its sign and the sample behind the baseline", () => {
    render(<HittingPeriodView summary={summary()} />);
    expect(screen.getByText(/\+4.0 mph/)).toBeInTheDocument();
    expect(screen.getAllByText(/vs previous \(8 balls\)/).length).toBeGreaterThan(0);
  });

  it("shows a drop without dressing it up", () => {
    render(<HittingPeriodView summary={summary()} />);
    expect(screen.getByText(/-0.9 mph/)).toBeInTheDocument();
  });

  it("says there is no comparison rather than reporting a change of zero", () => {
    const first = summary({
      best_exit_velocity_change: {
        current: 95,
        previous: null,
        delta: null,
        percent_change: null,
        current_sample: 12,
        previous_sample: 0,
      },
    });
    render(<HittingPeriodView summary={first} />);
    expect(screen.getAllByText("No earlier period to compare").length).toBeGreaterThan(0);
  });
});

describe("a measurement that is missing", () => {
  it("renders an em dash, never a zero", () => {
    const nothingMeasured = summary({
      batted_balls: 0,
      best_exit_velocity_mph: null,
      average_exit_velocity_mph: null,
      sweet_spot_rate: null,
      sweet_spot_count: 0,
    });
    render(<HittingPeriodView summary={nothingMeasured} />);

    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });
});
