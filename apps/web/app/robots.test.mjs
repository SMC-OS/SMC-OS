/**
 * Sprint 034 (Phase 2) — the application host must stay out of the index
 * in every environment.
 *
 * Guards two real harms, not a style preference: the login page
 * outranking geocore.one for brand queries, and token-scoped portal or
 * invite URLs (capability tokens, not login-protected pages) being
 * crawled and archived.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const robots = await readFile(new URL("./robots.ts", import.meta.url), "utf8");

test("the application disallows all crawling", () => {
  assert.match(robots, /userAgent:\s*["']\*["']/);
  assert.match(robots, /disallow:\s*["']\/["']/);
});

test("the disallow is unconditional, not environment-dependent", () => {
  // An APP_ENV check here would leave a preview or misconfigured host
  // indexable — the exact failure this file exists to prevent.
  const code = robots.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  assert.doesNotMatch(code, /process\.env/);
  // Lookbehind so the legitimate `disallow:` does not match.
  assert.doesNotMatch(code, /(?<!dis)allow:/i);
});
