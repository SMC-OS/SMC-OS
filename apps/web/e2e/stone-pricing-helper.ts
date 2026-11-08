import type { Page } from "@playwright/test";

/** Explicit synthetic prices: the editor must never supply these itself. */
export async function setStoneJobPrice(page: Page, value = "1200") {
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if ((await material.isVisible()) && !(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  await page
    .getByLabel("Your job price before discount and VAT (£)")
    .fill(value);
}
