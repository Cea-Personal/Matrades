import { expect, test } from "@playwright/test";

test("unauthenticated visitors see the TraderX login boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TraderX" })).toBeVisible();
  await expect(page.getByText("Authenticate to access the Command Center.")).toBeVisible();
  await expect(page.getByRole("form", { name: "TraderX sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Set up the initial owner" })).toBeVisible();
});
