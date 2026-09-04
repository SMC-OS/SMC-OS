/**
 * Sprint 034 (Phase 3) — the Enterprise CTA must never ship a hardcoded
 * mailbox address.
 *
 * A public "Contact sales" link is only worth anything if the mailbox
 * actually exists. One that bounces loses the most valuable enquiry on the
 * pricing page, and loses it silently — no error, no bounce the visitor
 * sees, just no reply. The pre-rebrand page linked `sales@simo-os.com`, on a
 * domain the business does not even own, which is exactly that failure
 * already shipped once.
 *
 * The address therefore comes from NEXT_PUBLIC_SALES_EMAIL, set at build
 * time by whoever can confirm the mailbox exists. With none set the CTA
 * routes to signup, which always works.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("./page.tsx", import.meta.url), "utf8");
// Strip comments so prose about the decision can neither satisfy nor break
// these assertions.
const code = page.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");

test("no hardcoded mailbox address anywhere on the pricing page", () => {
  assert.doesNotMatch(code, /mailto:[a-z0-9._%+-]+@/i);
});

test("the sales address comes from the environment", () => {
  assert.match(code, /process\.env\.NEXT_PUBLIC_SALES_EMAIL/);
});

test("an unset address falls back to a route that always works", () => {
  // Guards against a future edit that renders a dead mailto (or nothing at
  // all) when the variable is absent.
  assert.match(code, /SALES_EMAIL\s*\?/);
  assert.match(code, /router\.push\(["']\/signup["']\)/);
});
