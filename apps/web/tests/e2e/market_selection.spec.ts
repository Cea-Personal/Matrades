import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("market research keeps exclusions separate from deliberate activation", async ({ page }) => {
  await mockReadyCommandCenter(page);
  await page.goto("/command-center");
  await expect(page.getByRole("button", { name: "Markets" })).toBeVisible();
  await page.getByRole("button", { name: "Markets" }).click();
  await expect(page.getByText(/research never changes an active market/i)).toBeVisible();
  for (const category of ["Commodity", "Forex", "Cryptocurrency"]) {
    await page.getByRole("button", { name: category, exact: true }).click();
    await page.getByRole("button", { name: `Run ${category} research` }).click();
    await expect(page.getByRole("heading", { name: "Market research report" })).toBeVisible();
    await page.getByRole("button", { name: "Review for activation" }).click();
    await page.getByLabel("Reason for this selection").fill(`Approve the eligible ${category} evidence`);
    await page.getByLabel(/I reviewed the eligibility evidence/i).check();
    await page.getByRole("button", { name: "Approve active market" }).click();
    await expect(page.getByRole("status")).toContainText("human-approved");
  }
  const activeMarkets = page.getByLabel("Human-approved active markets");
  await expect(activeMarkets.getByText("XAUUSD", { exact: true })).toBeVisible();
  await expect(activeMarkets.getByText("EURUSD", { exact: true })).toBeVisible();
  await expect(activeMarkets.getByText("BTCUSD", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Review deactivation" }).first().click();
  await page.getByLabel("Reason for deactivation").fill("Pause this market for an evidence review");
  await page.getByRole("button", { name: "Confirm deactivation" }).click();
  await expect(page.getByRole("status")).toContainText("did not select a replacement");
});
