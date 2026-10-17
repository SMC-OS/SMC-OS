import type { Page } from "@playwright/test";

export async function prepareStoneQuoteEditor(
  page: Page,
  options: { openAiDraft?: boolean } = {},
) {
  await page.getByLabel("Show all sections").check();

  if (options.openAiDraft) {
    await page.getByText("Draft with AI (optional)", { exact: true }).click();
  }
}
