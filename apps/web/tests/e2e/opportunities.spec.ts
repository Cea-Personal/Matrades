import { expect, test } from "@playwright/test";

test("recommendations never become an execution control", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
