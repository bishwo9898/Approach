import { describe, expect, it } from "vitest";

import { MIN_LENGTH, passwordProblems, passwordStrength } from "@/lib/password";

/**
 * These mirror `apps/api/tests/unit/test_password_policy.py`. The server is the
 * only thing that decides -- this copy exists so the field can say what is
 * wrong while someone types -- so the cases are deliberately the same shape.
 */
describe("passwordProblems", () => {
  it("accepts a reasonable password", () => {
    expect(passwordProblems("RisingFastball26")).toEqual([]);
  });

  it.each([
    ["Short1", `at least ${MIN_LENGTH}`],
    ["nodigitsatall", "one number"],
    ["12345678901", "one letter"],
    ["aaaaaaaaaa1", "variety"],
    [" Leading12345", "space at the start"],
    ["Trailing12345 ", "space at the start"],
  ])("rejects %s", (password, fragment) => {
    const problems = passwordProblems(password);
    expect(problems.length).toBeGreaterThan(0);
    expect(problems.some((p) => p.includes(fragment))).toBe(true);
  });

  it("reports every problem at once rather than one per submit", () => {
    expect(passwordProblems("abc").length).toBeGreaterThanOrEqual(2);
  });

  it("rejects a password that restates the email it protects", () => {
    const problems = passwordProblems("jordanavery99", {
      email: "jordan.avery@approach.com",
    });
    expect(problems.some((p) => p.includes("name or email"))).toBe(true);
  });

  it("allows a password that merely shares letters with the email", () => {
    expect(
      passwordProblems("RisingFastball26", { email: "jordan.avery@approach.com" }),
    ).toEqual([]);
  });

  it("ignores a short email local part, which would ban most words", () => {
    expect(passwordProblems("Tigerswing12", { email: "ty@approach.com" })).toEqual([]);
  });

  it("says nothing about an empty field beyond the length rule", () => {
    // An untouched field must not shout about character variety.
    expect(passwordProblems("")).toEqual([
      `Use at least ${MIN_LENGTH} characters.`,
      "Include at least one letter.",
      "Include at least one number.",
    ]);
  });
});

describe("passwordStrength", () => {
  it("is zero while the password is unacceptable", () => {
    expect(passwordStrength("short")).toBe(0);
  });

  it("rises with length and character range", () => {
    expect(passwordStrength("GoodSwing2026")).toBeGreaterThan(0);
    expect(passwordStrength("Good-Swing-2026!")).toBeGreaterThan(
      passwordStrength("goodswing2026"),
    );
  });
});
