import type { Page } from "@playwright/test";

export async function showAllStoneQuoteSections(page: Page) {
  await page.getByLabel("Show all sections").check();
}
