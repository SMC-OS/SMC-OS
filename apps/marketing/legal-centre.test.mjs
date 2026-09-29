import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const legal = await readFile(new URL("./lib/legal.ts", import.meta.url), "utf8");
const index = await readFile(new URL("./app/legal/page.tsx", import.meta.url), "utf8");

const documents = [
  "privacy-policy", "terms-of-service", "cookie-policy", "acceptable-use-policy",
  "copyright-takedown-policy", "data-processing-agreement", "subprocessors",
];

test("Legal Centre publishes all seven substantive document routes", () => {
  for (const slug of documents) assert.match(legal, new RegExp(`slug: "${slug}"`));
  assert.match(index, /LEGAL_DOCUMENTS\.map/);
});

test("Legal Centre keeps pending facts and prohibited claims out of customer copy", () => {
  assert.match(legal, /registration is in progress/i);
  assert.match(legal, /does not state an ICO registration number/i);
  assert.match(legal, /does not represent that it has a registered US DMCA designated agent/i);
  assert.doesNotMatch(legal, /VAT registered|Companies House number:\s*\d|SOC 2 certified|ISO 27001 certified/i);
  assert.doesNotMatch(legal, /\bTODO\b|\bTBD\b|lorem ipsum|placeholder/i);
});

test("privacy and cookie policy preserve the implemented consent and deletion boundaries", () => {
  assert.match(legal, /30-day recovery period/i);
  assert.match(legal, /does not initialise.*before marketing consent/i);
  assert.match(legal, /do not promise that every category is erased exactly 30 days/i);
});
