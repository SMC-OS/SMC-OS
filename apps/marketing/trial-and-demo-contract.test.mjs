/**
 * Phase B — the trial is a 14-day free trial with NO card required, and
 * every trial surface must say so and never contradict it. (History: the
 * Sprint 041 version of this file enforced the opposite, card-required
 * contract; the owner has since approved the no-card trial.) Also guards
 * the shape of the Request Demo form and its success copy.
 *
 * Same static source-text pattern as indexability.test.mjs/
 * positioning.test.mjs — cheap in CI, fails on the exact copy or field
 * regression it targets.
 */

import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

const pricingClient = await read("./app/pricing/page-client.tsx");
const pricingPage = await read("./app/pricing/page.tsx");
const homepage = await read("./app/page.tsx");
const trialDisclosure = await read("./components/TrialDisclosure.tsx");
const demoFormClient = await read("./app/request-demo/page-client.tsx");
const demoApi = await read("./lib/api.ts");

async function sourceFiles(dir) {
  const out = [];
  for (const entry of await readdir(new URL(dir, import.meta.url), { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) out.push(...(await sourceFiles(path)));
    else if (/\.(tsx?|mjs)$/.test(entry.name)) out.push(path);
  }
  return out;
}

test("no public surface says the trial needs a card or charges anything up front", async () => {
  const forbidden = [
    /card is required/i,
    /card required to activate/i,
    /card required, £0/i,
    /payment method is required/i,
    /£0 (is )?due today/i,
    /before you add a card/i,
  ];
  for (const path of [...(await sourceFiles("./app")), ...(await sourceFiles("./components"))]) {
    const source = await read(path);
    for (const pattern of forbidden) {
      assert.doesNotMatch(source, pattern, `${path} contradicts the no-card trial (${pattern})`);
    }
  }
});

test("every trial surface states the 14-day free trial needs no card", () => {
  for (const [name, source] of [
    ["pricing page", pricingClient],
    ["pricing metadata", pricingPage],
    ["homepage", homepage],
    ["trial disclosure component", trialDisclosure],
  ]) {
    assert.match(source, /No card required/, `${name} must say "No card required"`);
  }
  assert.match(homepage, /day free trial\. No card required\./);
});

test("the trial disclosure never promises an automatic charge", () => {
  assert.doesNotMatch(trialDisclosure, /will be charged on/i);
  assert.match(trialDisclosure, /Nothing is charged when your trial ends/);
  // Trial length and price come from the plan data, never a literal.
  assert.match(trialDisclosure, /plan\.trial_days/);
  assert.doesNotMatch(trialDisclosure, /trial_days\s*=\s*14/);
});

test("pricing is rendered from the drift-tested catalogue, not fetched at runtime", () => {
  assert.match(pricingClient, /from "@\/lib\/pricing"/);
  assert.doesNotMatch(pricingClient, /fetchPlans|Loading plans/);
  assert.doesNotMatch(demoApi, /fetchPlans/);
});

test("trial CTAs carry the chosen plan and billing period to signup", () => {
  assert.match(pricingClient, /signup\?plan=\$\{plan\.plan\}&billing_period=\$\{period\}/);
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
