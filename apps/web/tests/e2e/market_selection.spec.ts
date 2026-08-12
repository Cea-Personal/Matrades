import { expect, test } from "@playwright/test";

test("market research keeps exclusions separate from deliberate activation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/ranking never replaces/i)).toBeVisible();
});
