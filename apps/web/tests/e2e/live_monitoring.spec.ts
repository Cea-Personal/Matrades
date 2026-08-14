import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("manual positions are monitored without execution", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedMonitoring: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Trade monitoring" }).click();
  await expect(page.getByRole("button", { name: "Refresh from MT5" })).toBeVisible();
  await expect(page.getByText(/never creates, changes, or closes/i)).toBeVisible();
  await page.getByRole("button", { name: "Refresh from MT5" }).click();
  await expect(page.getByRole("status")).toContainText("1 account");
  await expect(page.getByText("RECOMMENDED", { exact: true })).toBeVisible();
  await expect(page.getByText("DISCRETIONARY", { exact: true })).toBeVisible();
  await expect(page.getByText("HEALTHY", { exact: true })).toBeVisible();
  const discretionary = page.getByRole("article").filter({ hasText: "XAUUSD" });
  await discretionary.getByRole("button", { name: "Monitor" }).click();
  await expect(page.getByText(/still included in shared account risk/i)).toBeVisible();
  await page.getByLabel("Classification").selectOption("UNRESOLVED");
  await page.getByLabel("Reason").fill("Broker position requires manual classification review");
  await page.getByRole("button", { name: "Record audited correction" }).click();
  await expect(page.getByRole("status")).toContainText("audited classification correction");
});
