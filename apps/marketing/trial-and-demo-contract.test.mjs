/**
 * GeoCore Premium OS Plan 02 (Sprint 041) — the Master Spec's single
 * hardest commercial-copy rule: the trial is card-required, and this app
 * must never say otherwise. Also guards the shape of the Request Demo
 * form (Task 11/18) and the demo success copy (Task 12) staying exact.
 *
 * Same static source-text pattern as indexability.test.mjs/
 * positioning.test.mjs — cheap in CI, fails on the exact copy or field
 * regression it targets.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pricingClient = await readFile(
  new URL("./app/pricing/page-client.tsx", import.meta.url),
  "utf8"
);
const trialDisclosure = await readFile(
  new URL("./components/TrialDisclosure.tsx", import.meta.url),
  "utf8"
);
const demoFormClient = await readFile(
  new URL("./app/request-demo/page-client.tsx", import.meta.url),
  "utf8"
);
const demoApi = await readFile(new URL("./lib/api.ts", import.meta.url), "utf8");

test("the trial surfaces never claim the trial requires no card", () => {
  // "No card required" is a legitimate, true claim about the SEPARATE
  // Request Demo path (which genuinely needs neither account nor card —
  // see the homepage's own demo section and request-demo/page-client.tsx)
  // — it must never appear on the trial/pricing surfaces specifically.
  for (const [name, source] of [
    ["pricing page", pricingClient],
    ["trial disclosure component", trialDisclosure],
  ]) {
    assert.doesNotMatch(source, /no card required/i, `${name} must never say "no card required"`);
  }
});

test("the trial disclosure component states £0 due today and the card requirement", () => {
  assert.match(trialDisclosure, /£0 due today/);
  assert.match(trialDisclosure, /payment method is required/i);
  assert.match(trialDisclosure, /will be charged on/i);
  // The trial length and price both come from the real plan data, never
  // a hard-coded "14" or "£" literal figure of the component's own.
  assert.match(trialDisclosure, /plan\.trial_days/);
  assert.doesNotMatch(trialDisclosure, /trial_days\s*=\s*14/);
});

test("the pricing page states the trial is card-required before any checkout handoff", () => {
  assert.match(pricingClient, /card is required/i);
  assert.match(pricingClient, /£0 is due today/i);
});

test("the request-demo form does not require an account", () => {
  assert.doesNotMatch(demoFormClient, /signup|login/i);
});

test("the request-demo form collects the specified fields and a honeypot", () => {
  for (const field of [
    "first_name",
    "last_name",
    "email",
    "phone",
    "company_name",
    "team_size",
    "trades",
    "current_system",
    "message",
    "preferred_contact_method",
    "website",
  ]) {
    assert.match(demoFormClient, new RegExp(field), `expected the demo form to collect ${field}`);
  }
  assert.match(demoFormClient, /honeypot/i);
});

test("the demo success state matches the specified copy exactly", () => {
  assert.match(demoFormClient, /Demo request received\./);
  assert.match(demoFormClient, /We&apos;ll contact you using the details you provided\./);
});

test("the demo request payload shape never includes a client-set id, status or source", () => {
  const interfaceBody = demoApi.slice(
    demoApi.indexOf("interface DemoRequestPayload"),
    demoApi.indexOf("}", demoApi.indexOf("interface DemoRequestPayload"))
  );
  for (const field of ["id", "status", "source"]) {
    assert.doesNotMatch(
      interfaceBody,
      new RegExp(`\\b${field}\\s*[?:]`),
      `DemoRequestPayload must not declare a client-settable "${field}" field`
    );
  }
});
