import { expect, test, type Page } from "@playwright/test";

async function signInForUi(page: Page) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "browser-user",
        owner_id: "browser-owner",
        email: "browser@example.com",
        email_verified: true,
        mfa_enabled: true,
        role: "TRADER",
      }),
    }),
  );
}

test("renders the autonomous operations workspace", async ({ page }) => {
  await signInForUi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Autonomous trading command center" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Trade desk" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Extras" })).toBeVisible();
});

test("renders strategy research and validation controls", async ({ page }) => {
  await signInForUi(page);
  await page.goto("/strategies");
  await expect(page.getByRole("heading", { name: "Strategy research & validation" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Generate strategy" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Run backtest" })).toBeVisible();
});
