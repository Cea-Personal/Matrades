import { expect, test } from "@playwright/test";

import { mockReadyCommandCenter } from "./support";

test("reviewed provider cards operate inside the existing Integrations workspace", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Integrations" }).click();

  await expect(page.getByRole("heading", { name: "Reviewed research providers" })).toBeVisible();
  for (const provider of ["CME Group", "Cboe FX Spot", "Coinbase Exchange", "OpenAI Responses", "Anthropic Messages"]) {
    await expect(page.getByText(provider, { exact: true })).toBeVisible();
  }
  await expect(page.getByText(/credentials are write-only/i)).toBeVisible();
  await expect(page.getByText(/licensing and retention/i)).toBeVisible();
  await expect(page.getByText(/Research OpenAI/)).toBeVisible();

  await page.getByRole("button", { name: "Test provider" }).click();
  await expect(page.getByRole("status")).toContainText("Qualification job qualification-job-1");

  await page.getByText("Rotate write-only credential").click();
  await page.getByLabel("New api key").fill("browser-only-secret");
  await page.getByRole("button", { name: "Rotate credential" }).click();
  await expect(page.getByRole("status")).toContainText("credential rotated");
  await expect(page.getByText("browser-only-secret")).toHaveCount(0);

  await page.getByRole("button", { name: "Disable provider" }).click();
  await expect(page.getByRole("status")).toContainText("disabled");
});
