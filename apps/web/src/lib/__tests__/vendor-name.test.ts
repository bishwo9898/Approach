import { describe, expect, it } from "vitest";

import { splitVendorName } from "@/lib/vendor-name";

describe("splitVendorName", () => {
  it("handles the 'Last, First' shape TrackMan reports", () => {
    expect(splitVendorName("Jones, Ryan")).toEqual({
      firstName: "Ryan",
      lastName: "Jones",
    });
  });

  it("handles a plain 'First Last' name", () => {
    expect(splitVendorName("Ryan Jones")).toEqual({
      firstName: "Ryan",
      lastName: "Jones",
    });
  });

  it("keeps a multi-word surname intact", () => {
    // Splitting on the last space would leave "Juan de la" as the first name.
    expect(splitVendorName("Juan de la Cruz")).toEqual({
      firstName: "Juan",
      lastName: "de la Cruz",
    });
  });

  it("treats a single token as a surname rather than guessing", () => {
    expect(splitVendorName("Ichiro")).toEqual({ firstName: "", lastName: "Ichiro" });
  });

  it("returns empty fields for missing or blank input", () => {
    expect(splitVendorName(null)).toEqual({ firstName: "", lastName: "" });
    expect(splitVendorName("   ")).toEqual({ firstName: "", lastName: "" });
  });

  it("trims stray whitespace around the comma", () => {
    expect(splitVendorName("  Cole ,  Marcus ")).toEqual({
      firstName: "Marcus",
      lastName: "Cole",
    });
  });
});
