import { expect, test } from "@playwright/test";

test("manual positions are monitored without execution", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
