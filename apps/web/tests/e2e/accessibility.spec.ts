import { expect, test } from "@playwright/test";

test("shell has an accessible main landmark", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
});
