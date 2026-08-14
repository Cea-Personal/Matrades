import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("strategy evidence is immutable and lifecycle-gated", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedActiveMarket: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Strategies" }).click();
  await expect(page.getByRole("heading", { name: "Define a deterministic strategy" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Immutable versions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run required validation" })).toBeDisabled();
  await page.getByLabel("Strategy name").fill("H1 trend continuation");
  await page.getByLabel("Entry value").fill("1.08");
  await page.getByLabel("Change summary").fill("Initial deterministic version");
  await page.getByRole("button", { name: "Save immutable draft" }).click();
  await page.getByRole("button", { name: "H1 trend continuation" }).click();
  await expect(page.getByText(/prerequisites remain unmet/i)).toBeVisible();
  await page.getByRole("button", { name: "Run reproducible backtest" }).click();
  await page.getByText("Frozen manifest and distributions", { exact: true }).click();
  await expect(page.getByText("backtest-manifest-hash", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run required validation" }).click();
  await expect(page.getByText(/Overall: PASS/i)).toBeVisible();
  await expect(page.getByText("validation-manifest-hash", { exact: true })).toBeVisible();
});
