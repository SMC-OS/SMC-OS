/**
 * Sprint 036 (Workstream C) — money and date formatting.
 *
 * Currency is the point of this file. GBP is now a default rather than an
 * assumption, and the regressions worth guarding are the ones that would
 * silently show the wrong symbol or the wrong day to a real customer.
 */

import { describe, expect, it } from "vitest";

import {
  currencySymbol,
  daysFromTodayISO,
  formatCurrency,
  formatCurrencyGBP,
  formatDate,
  formatMoney,
  todayISO,
} from "./utils";

describe("money formatting", () => {
  it("defaults to GBP but honours another currency", () => {
    expect(formatCurrency(1250)).toContain("£");
    expect(formatCurrency(1250, "EUR")).toContain("€");
    expect(formatCurrency(1250, "USD")).toContain("$");
  });

  it("keeps formatCurrencyGBP working for every existing call site", () => {
    expect(formatCurrencyGBP(1250)).toBe(formatCurrency(1250, "GBP"));
  });

  it("shows pence where a figure will actually be checked", () => {
    // A headline tile rounds; a quote line must not.
    expect(formatCurrency(1250.5)).not.toContain(".50");
    expect(formatMoney(1250.5)).toContain(".50");
  });

  it("returns a symbol for a supported currency and the code otherwise", () => {
    expect(currencySymbol("GBP")).toBe("£");
    expect(currencySymbol("EUR")).toBe("€");
    // Never a wrong symbol — the code is the honest fallback.
    expect(currencySymbol("ZZZ")).toBe("ZZZ");
  });
});

describe("date formatting", () => {
  it("renders a calendar date on the day it actually is", () => {
    // The classic bug: parsing "2026-01-01" as UTC midnight and
    // rendering it in a negative-offset timezone shows 31 December.
    expect(formatDate("2026-01-01")).toBe("1 Jan 2026");
    expect(formatDate("2026-12-31")).toBe("31 Dec 2026");
  });

  it("renders an em dash rather than 'Invalid Date' for a missing value", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("produces today's local date, not yesterday's UTC one", () => {
    const now = new Date();
    const expected = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-");
    expect(todayISO()).toBe(expected);
  });

  it("offsets by whole days for a quote validity default", () => {
    expect(daysFromTodayISO(0)).toBe(todayISO());
    expect(daysFromTodayISO(30)).not.toBe(todayISO());
    expect(daysFromTodayISO(30)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
