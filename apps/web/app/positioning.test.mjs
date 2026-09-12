/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 7 — the app's own
 * metadata (layout.tsx) had already been corrected to trade-neutral
 * positioning, but the PWA manifest had drifted and still claimed
 * "stone and construction businesses". Both must say the same thing:
 * GeoCore is the AI operating system for construction and renovation
 * businesses, not a stone-first product with construction as an
 * afterthought.
 *
 * Static source-text assertions, same pattern as robots.test.mjs.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const layout = await readFile(new URL("./layout.tsx", import.meta.url), "utf8");
const manifest = await readFile(new URL("./manifest.ts", import.meta.url), "utf8");

test("the app's own metadata positions GeoCore as trade-neutral, not stone-first", () => {
  assert.match(layout, /construction and renovation businesses/i);
  assert.doesNotMatch(layout, /stone and construction/i);
});

test("the PWA manifest matches the app's own metadata rather than drifting from it", () => {
  assert.match(manifest, /construction and renovation businesses/i);
  assert.doesNotMatch(manifest, /stone and construction/i);
});
