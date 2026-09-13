import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricCard } from "@/components/metric-card";
import type { MetricSummary } from "@/lib/types";

const summary = (overrides: Partial<MetricSummary> = {}): MetricSummary => ({
  definition: {
    id: "m1",
    key: "pitch.fastball.max_velocity",
    display_name: "Fastball Max Velocity",
    description: null,
    category: "PITCHING",
    unit: "mph",
    aggregation: "MAX",
    record_direction: "HIGHER_IS_BETTER",
    display_precision: 1,
    min_sample_size: 3,
    is_headline: true,
    calculation_version: 1,
  },
  latest: {
    value: 87.3,
    unit: "mph",
    sample_size: 22,
    source_status: "PRELIMINARY",
    observed_on: "2026-09-12",
  },
  window: {
    current: 87.3,
    previous: 84.9,
    delta: 2.4,
    percent_change: 2.83,
    current_sample: 60,
    previous_sample: 55,
  },
  // Standing record set on an earlier day, deliberately different from the
  // latest value so assertions below are unambiguous.
  record: {
    metric_key: "pitch.fastball.max_velocity",
    metric_display_name: "Fastball Max Velocity",
    unit: "mph",
    display_precision: 1,
    value: 88.9,
    sample_size: 26,
    achieved_on: "2026-08-22",
    session_id: "s1",
    source_status: "VERIFIED",
    is_manual_override: false,
  },
  ...overrides,
});

describe("MetricCard", () => {
  it("shows the value with its unit", () => {
    render(<MetricCard summary={summary()} range="30d" />);

    expect(screen.getByText("87.3 mph")).toBeInTheDocument();
  });

  it("shows the standing record alongside the current value", () => {
    render(<MetricCard summary={summary()} range="30d" />);

    expect(screen.getByText("88.9 mph")).toBeInTheDocument();
  });

  it("always shows the sample size behind the number", () => {
    render(<MetricCard summary={summary()} range="30d" />);

    expect(screen.getByText("n=22")).toBeInTheDocument();
  });

  it("labels preliminary data so it is not mistaken for confirmed", () => {
    render(<MetricCard summary={summary()} range="30d" />);

    expect(screen.getByText("Preliminary")).toBeInTheDocument();
  });

  it("marks verified data as verified", () => {
    render(
      <MetricCard
        summary={summary({
          latest: {
            value: 87.3,
            unit: "mph",
            sample_size: 22,
            source_status: "VERIFIED",
            observed_on: "2026-09-12",
          },
        })}
        range="30d"
      />,
    );

    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("renders a gain as positive for a higher-is-better metric", () => {
    render(<MetricCard summary={summary()} range="30d" />);

    expect(screen.getByText(/\+2\.4/)).toHaveClass("text-positive");
  });

  it("renders a drop as negative without any risk or injury language", () => {
    const { container } = render(
      <MetricCard
        summary={summary({
          window: {
            current: 84.0,
            previous: 87.3,
            delta: -3.3,
            percent_change: -3.78,
            current_sample: 20,
            previous_sample: 22,
          },
        })}
        range="30d"
      />,
    );

    expect(screen.getByText(/−3\.3/)).toHaveClass("text-negative");
    expect(container.textContent?.toLowerCase()).not.toMatch(/injur|risk|warning sign/);
  });

  it("shows an em dash rather than zero when there is no data", () => {
    render(
      <MetricCard
        summary={summary({
          latest: {
            value: null,
            unit: "mph",
            sample_size: 0,
            source_status: null,
            observed_on: null,
          },
          record: null,
        })}
        range="30d"
      />,
    );

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("no samples")).toBeInTheDocument();
    expect(screen.getByText("No record yet")).toBeInTheDocument();
  });
});
