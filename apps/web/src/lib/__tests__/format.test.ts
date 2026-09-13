import { describe, expect, it } from "vitest";

import {
  changeTone,
  formatDate,
  formatDelta,
  formatMeasurement,
  formatSample,
} from "@/lib/format";

describe("formatMeasurement", () => {
  it("always attaches the unit", () => {
    expect(formatMeasurement(87.34, "mph", 1)).toBe("87.3 mph");
    expect(formatMeasurement(2184.6, "rpm", 0)).toBe("2185 rpm");
    expect(formatMeasurement(363, "ft", 0)).toBe("363 ft");
  });

  it("renders percentages without a space", () => {
    expect(formatMeasurement(64.2, "%", 1)).toBe("64.2%");
  });

  it("renders counts bare -- 'count' is not a unit anyone reads", () => {
    expect(formatMeasurement(28, "count", 0)).toBe("28");
  });

  it("distinguishes no data from zero", () => {
    // The single most important formatting rule: a missing measurement must
    // never render as 0.
    expect(formatMeasurement(null, "mph")).toBe("—");
    expect(formatMeasurement(undefined, "mph")).toBe("—");
    expect(formatMeasurement(0, "mph", 1)).toBe("0.0 mph");
  });
});

describe("formatDelta", () => {
  it("always shows the sign", () => {
    expect(formatDelta(2.4, 1)).toBe("+2.4");
    expect(formatDelta(-0.7, 1)).toBe("−0.7");
  });

  it("reports a negligible change as no change rather than +0.0", () => {
    expect(formatDelta(0, 1)).toBe("no change");
    expect(formatDelta(0.01, 1)).toBe("no change");
  });

  it("returns null when there is nothing to compare against", () => {
    expect(formatDelta(null)).toBeNull();
    expect(formatDelta(undefined)).toBeNull();
  });
});

describe("changeTone", () => {
  it("treats a rise as an improvement for higher-is-better metrics", () => {
    expect(changeTone(1.2, "HIGHER_IS_BETTER")).toBe("positive");
    expect(changeTone(-1.2, "HIGHER_IS_BETTER")).toBe("negative");
  });

  it("inverts for lower-is-better metrics", () => {
    expect(changeTone(-0.4, "LOWER_IS_BETTER")).toBe("positive");
    expect(changeTone(0.4, "LOWER_IS_BETTER")).toBe("negative");
  });

  it("stays neutral for volume metrics, which are not achievements", () => {
    expect(changeTone(50, "NONE")).toBe("neutral");
    expect(changeTone(0, "HIGHER_IS_BETTER")).toBe("neutral");
    expect(changeTone(null, "HIGHER_IS_BETTER")).toBe("neutral");
  });
});

describe("formatDate", () => {
  it("does not shift a calendar date by the viewer's timezone", () => {
    // A session dated 2026-09-12 must read as Sep 12 everywhere, including
    // west of UTC where naive parsing lands on the 11th.
    expect(formatDate("2026-09-12")).toBe("Sep 12, 2026");
    expect(formatDate("2026-01-01")).toBe("Jan 1, 2026");
  });

  it("handles missing and malformed values", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("nonsense")).toBe("—");
  });
});

describe("formatSample", () => {
  it("labels the evidence behind an aggregate", () => {
    expect(formatSample(24)).toBe("n=24");
  });
});
