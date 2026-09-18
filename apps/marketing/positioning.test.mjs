/**
 * GeoCore Premium OS Plan 02 (Sprint 041) / Master Spec §25 — ADR-043.
 *
 * SUPERSEDES the Sprint 039 Blocker 7 contract this file used to encode
 * ("construction and renovation businesses", explicitly forbidding "stone
 * and construction"). That was a deliberate de-emphasis of stone as the
 * platform's *assumed default* — correct in isolation, but it went
 * further and erased stone from the top-level positioning entirely. The
 * Master Spec's approved product direction is explicit and verbatim:
 * "GeoCore — The Operating System for Stone & Construction," with stone
 * shown as a first-class specialist capability *inside* that platform,
 * never as the whole identity and never omitted from it. See
 * docs/DECISIONS.md ADR-043 for the full reasoning.
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

// JSX text is HTML-entity-decoded at compile time (this codebase's own
// convention — see e.g. apps/web/app/pricing/page.tsx's "won&apos;t"), so
// page.tsx's raw source may spell the ampersand as the literal character
// or as the "&amp;" entity; both render identically. Match either.
const AMPERSAND = /&(?:amp;)?|and/i;

test("the site tagline/description position GeoCore as Stone & Construction, not stone-only", () => {
  assert.match(site, new RegExp(`Stone (?:${AMPERSAND.source}) Construction`, "i"));
  // Never narrows to a stone-only claim.
  assert.doesNotMatch(site, /operating system for stone\b(?! *(&|and) *construction)/i);
});

test("the homepage hero states the Stone & Construction positioning", () => {
  assert.match(
    page,
    new RegExp(`<h1>[\\s\\S]*Stone (?:${AMPERSAND.source}) Construction[\\s\\S]*<\\/h1>`, "i")
  );
});

test("the homepage never positions GeoCore as stone-only", () => {
  // Construction must remain visibly first-class alongside stone
  // somewhere on the page — not merely mentioned once in the hero.
  const constructionMentions = (page.match(/construction/gi) ?? []).length;
  assert.ok(
    constructionMentions >= 2,
    "expected the homepage to name construction more than once, never as a stone-only afterthought"
  );
});

test("the same SITE_DESCRIPTION feeds the meta description, Open Graph and structured data", () => {
  // A single correction in lib/site.ts must not be undermined by a
  // second, independent, drifted copy of the claim living in page.tsx.
  assert.doesNotMatch(page, /operating system for construction and renovation businesses/i);
});
