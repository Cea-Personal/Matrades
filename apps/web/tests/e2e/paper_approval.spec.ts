import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("paper evidence ends in deliberate approval", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedPaperEvidence: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Paper trading" }).click();
  await expect(page.getByText(/Paper evidence never promotes itself/i)).toBeVisible();
  await page.getByRole("button", { name: "Run paper evaluation" }).click();
  await expect(page.getByText(/All paper evidence thresholds passed/i)).toBeVisible();
  await page.getByLabel("Decision reason").fill("Evidence is current and performance remains within reviewed limits");
  await page.getByLabel("MFA code for live approval").fill("123456");
  await page.getByLabel(/I understand this grants decision-support eligibility only/i).check();
  await page.getByRole("button", { name: "Approve for live decision support" }).click();
  await expect(page.getByRole("status")).toContainText("APPROVE LIVE");
});
