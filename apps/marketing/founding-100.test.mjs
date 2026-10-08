/**
 * Founding 100 launch page: static source contract.
 *
 * Same pattern as positioning.test.mjs and indexability.test.mjs: cheap
 * source-text assertions that fail on the exact edit that would break the
 * approved offer, the CTA hierarchy, the no-fake-proof rule or discoverability.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("./app/founding-100/page.tsx", import.meta.url), "utf8");
const sitemap = await readFile(new URL("./app/sitemap.ts", import.meta.url), "utf8");
const site = await readFile(new URL("./lib/site.ts", import.meta.url), "utf8");
const layout = await readFile(new URL("./app/layout.tsx", import.meta.url), "utf8");
const home = await readFile(new URL("./app/page.tsx", import.meta.url), "utf8");
const footer = await readFile(new URL("./components/Footer.tsx", import.meta.url), "utf8");

test("the primary CTA is Join the Founding 100 and the secondary is Book a Demo", () => {
  const primary = page.search(/button--primary start-hero__cta[\s\S]*?Join the Founding 100/);
  const secondary = page.search(/button--secondary start-hero__demo[\s\S]*?Book a Demo/);
  assert.ok(primary > -1, "hero primary CTA (Join the Founding 100) missing");
  assert.ok(secondary > primary, "Book a Demo must be the secondary CTA, after the primary");
  // The primary CTA carries the signup URL; the secondary goes to the demo form.
  assert.match(page, /const SIGNUP_URL = `\$\{APP_URL\}\/signup`/);
  assert.match(page, /const DEMO_URL = "\/request-demo"/);
});

test("the hero and workflow carry the approved headline and workflow", () => {
  assert.match(page, /Run your stone &amp; construction business on one system\./);
  for (const step of ["Enquiry", "Quote", "Customer", "Material", "Project", "Documents & Photos", "Team", "Follow-up"]) {
    assert.ok(page.includes(`"${step}"`), `workflow step missing: ${step}`);
  }
});

test("the page states the approved Founding 100 offer", () => {
  for (const item of [
    "The first 100 businesses",
    "no card required",
    "Personal founder onboarding",
    "Assisted initial setup and import",
    "Direct access to the founder",
    "Influence over the roadmap",
    "Early access to new capabilities",
    "Permanent Founding 100 recognition",
    "Launch-price protection for 24 months",
  ]) {
    assert.ok(page.includes(item), `offer item missing: ${item}`);
  }
});

test("the page makes no unapproved promise and shows no invented proof", () => {
  // Checked against the code and copy only: comments may name the rules they enforce.
  const copy = page.replace(/\/\*[\s\S]*?\*\/|^\s*\/\/.*$/gm, "");
  // Offer rules: no lifetime access or discount, no automatic billing, no scarcity counter.
  assert.doesNotMatch(copy, /lifetime/i);
  assert.doesNotMatch(copy, /free forever/i);
  assert.doesNotMatch(copy, /automatic(ally)? (billed|charged|bill|charge)/i);
  assert.doesNotMatch(copy, /\b(spots?|places?|seats?) (left|remaining)\b/i);
  assert.doesNotMatch(copy, /only \d+ /i);
  assert.doesNotMatch(copy, /hurry|last chance|ends (soon|today)/i);
  // No testimonials or unsupported numbers.
  assert.doesNotMatch(copy, /testimonial/i);
  assert.doesNotMatch(copy, /"[^"]{20,}"\s*[-—]\s*[A-Z]/);
  assert.doesNotMatch(copy, /\b(save|saves|saving)\b[^.]{0,40}\d/i);
  assert.doesNotMatch(copy, /\b\d+% /);
});

test("the page uses the disambiguated GeoCore OS brand in its public metadata", () => {
  assert.match(site, /SEO_NAME = "GeoCore OS"/);
  assert.match(site, /SEO_LONG_NAME = "GeoCore OS — Stone & Construction Operating System"/);
  assert.match(page, /siteName: SEO_NAME/);
  assert.match(page, /GeoCore OS is stone and construction business software/);
  assert.match(layout, /template: `%s \| \$\{SEO_NAME\}`/);
  assert.match(home, /title: `\$\{SEO_NAME\}: \$\{SITE_TAGLINE\}`/);
});

test("the homepage restates its Open Graph fields instead of dropping them", () => {
  // A page-level openGraph replaces the layout's object, so the title,
  // description, url and site name must be present on the page itself.
  const og = home.slice(home.indexOf("openGraph:"), home.indexOf("openGraph:") + 400);
  for (const key of ["title:", "description:", "url:", "siteName:", "images:"]) {
    assert.ok(og.includes(key), `homepage openGraph is missing ${key}`);
  }
});

test("the page is indexable, canonical, in the sitemap and linked from the footer", () => {
  assert.doesNotMatch(page, /index:\s*false/);
  assert.doesNotMatch(page, /robots:\s*\{/);
  assert.match(page, /const CANONICAL = `\$\{SITE_URL\}\/founding-100`/);
  assert.match(page, /alternates:\s*\{\s*canonical:\s*CANONICAL\s*\}/);
  assert.match(sitemap, /\/founding-100/);
  assert.match(footer, /href="\/founding-100"/);
});

test("tracking reuses the consent-gated tracker and sends no personal data", () => {
  assert.match(page, /from "\.\.\/start\/start-client"/);
  assert.match(page, /FoundingTracker/);
  assert.doesNotMatch(page, /fbq|gtag|googletagmanager|fetch\(|sendBeacon/);
});
