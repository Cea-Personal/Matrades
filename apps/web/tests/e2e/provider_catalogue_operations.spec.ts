import { expect, test } from "@playwright/test";

import { mockReadyCommandCenter } from "./support";

test("reviewed provider cards operate inside the existing Integrations workspace", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  await page.goto("/command-center");
  await expect(page.getByRole("complementary", { name: "Safe activation checklist" }).getByText("LiteLLM Gateway connection")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Safe activation checklist" }).getByText("Optional · done")).toBeVisible();
  const checklist = page.getByRole("complementary", { name: "Safe activation checklist" });
  await checklist.getByRole("button", { name: "Open Integrations workspace" }).click();

  await expect(page.getByRole("heading", { name: "Reviewed research providers" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Healthy connections" })).toBeVisible();
  await expect(page.locator(".active-market-grid strong", { hasText: "LiteLLM Gateway" })).toBeVisible();
  for (const provider of ["CME Group", "Cboe FX Spot", "Coinbase Exchange"]) {
    await expect(page.locator(".active-market-grid strong", { hasText: provider })).toHaveCount(0);
    await expect(page.getByRole("option", { name: provider })).toHaveCount(1);
  }
  await expect(page.getByText(/credentials are write-only/i)).toBeVisible();
  await expect(page.getByText(/licensing and retention/i)).toBeVisible();
  await expect(page.getByText(/Research LiteLLM/)).toBeVisible();
  await expect(page.getByRole("option", { name: "OpenAI Responses" })).toHaveCount(0);
  await expect(page.getByRole("option", { name: "Anthropic Messages" })).toHaveCount(0);

  await page.locator("#provider-kind").selectOption("LITELLM_PROXY");
  await expect(page.getByText(/LiteLLM keeps the underlying provider credentials/i)).toBeVisible();
  await expect(page.locator('input[name="configuration-base_url"]')).toHaveValue("http://litellm:4000/v1");
  await expect(page.locator('input[name="credential-virtual_key"]')).toBeVisible();

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
