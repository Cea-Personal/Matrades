import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("recommendations never become an execution control", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedOpportunities: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Opportunities" }).click();
  await expect(page.getByRole("button", { name: "Evaluate current opportunities" })).toBeVisible();
  await expect(page.getByText(/no endpoint or adapter that submits an order/i)).toBeVisible();
  await page.getByRole("button", { name: "Evaluate current opportunities" }).click();
  await expect(page.getByText("PASS_REDUCED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review" }).click();
  await expect(page.getByText("1.085", { exact: true })).toBeVisible();
  await expect(page.getByText("Manual only", { exact: true })).toBeVisible();
  await expect(page.getByText(/REDUCED RISK STATE OR SECOND POSITION/i)).toBeVisible();
});
