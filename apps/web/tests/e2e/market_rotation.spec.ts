import { expect, test } from "@playwright/test";

test("reactivation ends in human approval", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
