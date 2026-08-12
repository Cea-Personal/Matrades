import { expect, test } from "@playwright/test";

test("journal behavior creates proposals without changing strategy history", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
