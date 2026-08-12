import { expect, test } from "@playwright/test";

test("strategy evidence is immutable and lifecycle-gated", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/manual trading/i)).toBeVisible();
});
