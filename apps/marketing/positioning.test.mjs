/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 7 — the locked
 * top-level positioning is "GeoCore — the AI operating system for
 * construction and renovation businesses." Stone and worktops remain a
 * supported specialist vertical, but must never again read as the
 * platform's assumed identity in the copy a search engine or a social
 * preview scrapes.
 *
 * Static source-text assertions, same pattern as indexability.test.mjs:
 * cheap in CI, and they fail on the exact edit that would regress this —
 * a copy change, not a behavioural one, so a build-time text check is the
 * right weight of test.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const site = await readFile(new URL("./lib/site.ts", import.meta.url), "utf8");
const page = await readFile(new URL("./app/page.tsx", import.meta.url), "utf8");

test("the site description positions GeoCore as trade-neutral, not stone-first", () => {
  assert.match(site, /construction and renovation businesses/i);
  assert.doesNotMatch(site, /stone and construction/i);
});

test("the homepage hero positions GeoCore as trade-neutral, not stone-first", () => {
  assert.match(page, /<h1>.*construction and renovation businesses.*<\/h1>/is);
  assert.doesNotMatch(page, /stone and construction/i);
});

test("the same SITE_DESCRIPTION feeds the meta description, Open Graph and structured data", () => {
  // A single correction in lib/site.ts must not be undermined by a second,
  // independent copy of the claim living in page.tsx itself.
  assert.doesNotMatch(page, /operating system for stone/i);
});
