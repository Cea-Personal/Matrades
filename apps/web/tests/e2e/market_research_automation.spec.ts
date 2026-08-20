import { expect, test } from "@playwright/test";

import { mockReadyCommandCenter } from "./support";

test("scheduled three-category research stays in Markets and keeps analysis advisory", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Markets" }).click();

  await expect(page.getByRole("heading", { name: "Market research automation" })).toBeVisible();
  await page.getByLabel("AI provider").selectOption("LITELLM_PROXY");
  await page.getByLabel("Model ID").fill("openrouter/google/gemini-2.5-pro");
  await page.getByLabel("Research interval").fill("3600");
  await page.getByLabel("Anchor start").fill("2026-08-14T09:00");
  await page.getByLabel("Account time zone").fill("UTC");
  await page.getByLabel("Enable recurring research").check();
  await page.getByLabel("Reason for research settings").fill("Run governed hourly market research");
  await page.getByRole("button", { name: "Save research settings" }).click();
  await expect(page.getByRole("status")).toContainText("future runs");

  await page.getByRole("button", { name: "Run all three categories" }).click();
  const report = page.getByRole("region", { name: "Coordinated market research" });
  await expect(report).toContainText("Commodity");
  await expect(report).toContainText("Forex");
  await expect(report).toContainText("Cryptocurrency");
  await expect(report).toContainText("ACTUAL");
  await expect(report).toContainText("BROKER_PROXY");
  await expect(report).toContainText("Ranking is not activation");
  await expect(report).toContainText("gpt-5.6-terra");
  await expect(report).toContainText("analysis unavailable");
  await expect(report).toContainText("Rank 1");
  await expect(report).toContainText("volatility");
  await expect(report).toContainText("Deterministic rationale");
  await expect(report).toContainText("advisory provider failure");
  await expect(report).toContainText("Commodity evidence is coherent");

  await report.getByRole("button", { name: "Retry Forex pinned analysis" }).click();
  await expect(page.getByRole("status")).toContainText("same pinned model");
  await expect(report.getByRole("button", { name: "Review Commodity proposal for activation" })).toBeVisible();
  await expect(report.getByRole("button", { name: "Review Forex proposal for activation" })).toBeVisible();
  await expect(report.getByRole("button", { name: /proposal for activation/ })).toHaveCount(2);
});
