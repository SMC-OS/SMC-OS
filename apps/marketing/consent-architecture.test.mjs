import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("marketing tracking uses the single versioned consent record", async () => {
  const [consent, tracker, banner] = await Promise.all([
    readFile(new URL("./lib/consent.ts", import.meta.url), "utf8"),
    readFile(new URL("./app/start/tracker.ts", import.meta.url), "utf8"),
    readFile(new URL("./components/ConsentBanner.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(consent, /geocore_consent/);
  assert.match(tracker, /hasConsent\("marketing"\)/);
  assert.match(tracker, /hasConsent\("analytics"\)/);
  assert.match(banner, /saveConsent/);
  assert.match(banner, /Cookie preferences/);
  assert.match(banner, /setVisible\(true\)/);
  assert.match(consent, /essential: true/);
});
