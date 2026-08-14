import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("replacement evidence and retained knowledge end in human approval", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedActiveMarket: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Markets" }).click();
  await expect(page.getByRole("heading", { name: "Market replacement review" })).toBeVisible();
  await expect(page.getByText("REVIEW REPLACEMENT")).toBeVisible();
  await expect(page.getByText(/EURUSD · 0.71/)).toBeVisible();
  await expect(page.getByText(/GBPUSD · 0.83/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Retained knowledge and reactivation" })).toBeVisible();
  await expect(page.getByText(/Every path ends in human market approval/i)).toBeVisible();
  await page.getByRole("button", { name: "Inspect retained knowledge" }).click();
  await expect(page.getByText("REVALIDATION_REQUIRED")).toBeVisible();
  await expect(page.getByText("8", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create governed plan" }).click();
  await expect(page.getByRole("status")).toContainText("was not automatically reactivated");
  await expect(page.getByText(/Automatic activation: no/)).toBeVisible();
});
