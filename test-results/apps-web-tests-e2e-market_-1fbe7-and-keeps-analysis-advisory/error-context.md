# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/tests/e2e/market_research_automation.spec.ts >> scheduled three-category research stays in Markets and keeps analysis advisory
- Location: apps/web/tests/e2e/market_research_automation.spec.ts:5:5

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/command-center", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | import { mockReadyCommandCenter } from "./support";
  4  | 
  5  | test("scheduled three-category research stays in Markets and keeps analysis advisory", async ({ page }) => {
  6  |   await mockReadyCommandCenter(page, { seedMarketAutomation: true });
> 7  |   await page.goto("/command-center");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  8  |   await page.getByRole("button", { name: "Markets" }).click();
  9  | 
  10 |   await expect(page.getByRole("heading", { name: "Market research automation" })).toBeVisible();
  11 |   await page.getByLabel("AI provider").selectOption("OPENAI_RESPONSES");
  12 |   await page.getByLabel("Model ID").fill("gpt-5.6-luna");
  13 |   await page.getByLabel("Research interval").fill("3600");
  14 |   await page.getByLabel("Anchor start").fill("2026-08-14T09:00");
  15 |   await page.getByLabel("Account time zone").fill("UTC");
  16 |   await page.getByLabel("Enable recurring research").check();
  17 |   await page.getByLabel("Reason for research settings").fill("Run governed hourly market research");
  18 |   await page.getByRole("button", { name: "Save research settings" }).click();
  19 |   await expect(page.getByRole("status")).toContainText("future runs");
  20 | 
  21 |   await page.getByRole("button", { name: "Run all three categories" }).click();
  22 |   const report = page.getByRole("region", { name: "Coordinated market research" });
  23 |   await expect(report).toContainText("Commodity");
  24 |   await expect(report).toContainText("Forex");
  25 |   await expect(report).toContainText("Cryptocurrency");
  26 |   await expect(report).toContainText("ACTUAL");
  27 |   await expect(report).toContainText("BROKER_PROXY");
  28 |   await expect(report).toContainText("Ranking is not activation");
  29 |   await expect(report).toContainText("gpt-5.6-terra");
  30 |   await expect(report).toContainText("analysis unavailable");
  31 |   await expect(report).toContainText("Rank 1");
  32 |   await expect(report).toContainText("volatility");
  33 |   await expect(report).toContainText("Deterministic rationale");
  34 |   await expect(report).toContainText("advisory provider failure");
  35 |   await expect(report).toContainText("Commodity evidence is coherent");
  36 | 
  37 |   await report.getByRole("button", { name: "Retry Forex pinned analysis" }).click();
  38 |   await expect(page.getByRole("status")).toContainText("same pinned model");
  39 |   await expect(report.getByRole("button", { name: "Review Commodity proposal for activation" })).toBeVisible();
  40 |   await expect(report.getByRole("button", { name: "Review Forex proposal for activation" })).toBeVisible();
  41 |   await expect(report.getByRole("button", { name: /proposal for activation/ })).toHaveCount(2);
  42 | });
  43 | 
```