/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 6 — the header logo
 * source asset is a raster crop from a flattened brand board (no vector
 * master exists; see docs/SPRINTS/sprint-039.md Sec 14.6). Next.js's image
 * optimizer re-encodes at quality 75 by default, which compounds that
 * existing softness with extra lossy compression for no reason.
 * `quality={100}` is a safe, source-preserving mitigation — it must not be
 * silently dropped by a future edit.
 *
 * Sprint 041 — the header (and its logo <Image>) moved out of app/page.tsx
 * into the shared components/Nav.tsx, reused by every public page
 * (homepage, /pricing, /request-demo) instead of only the homepage
 * duplicating it. Same assertion, same reasoning, now pointed at where
 * the logo actually lives.
 *
 * Static source-text assertion, same pattern as indexability.test.mjs:
 * cheap in CI, fails on the exact edit that would regress it.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const nav = await readFile(new URL("./components/Nav.tsx", import.meta.url), "utf8");

test("the header logo requests full quality from the Next.js image optimizer", () => {
  const headerImage = nav.slice(
    nav.indexOf('src="/brand/horizontal-logo.png"'),
    nav.indexOf("/>", nav.indexOf('src="/brand/horizontal-logo.png"'))
  );
  assert.match(headerImage, /quality=\{100\}/);
});
