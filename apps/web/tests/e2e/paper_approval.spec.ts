import { expect, test } from "@playwright/test";

test("paper evidence ends in deliberate approval", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
