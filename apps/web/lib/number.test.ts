import { describe, expect, it } from "vitest";

import { parseNumberInput } from "@/lib/number";

describe("parseNumberInput (post-release remediation §6)", () => {
  it("strips a leading zero exactly like a native type=number input would", () => {
    expect(parseNumberInput("05")).toBe(5);
    expect(parseNumberInput("007")).toBe(7);
    expect(parseNumberInput("00")).toBe(0);
  });

  it("parses a plain integer or decimal", () => {
    expect(parseNumberInput("12")).toBe(12);
    expect(parseNumberInput("2.5")).toBe(2.5);
  });

  it("falls back to the given default for empty or non-numeric input", () => {
    expect(parseNumberInput("")).toBe(0);
    expect(parseNumberInput("", 1)).toBe(1);
    expect(parseNumberInput("abc")).toBe(0);
    expect(parseNumberInput("abc", 3)).toBe(3);
  });
});
