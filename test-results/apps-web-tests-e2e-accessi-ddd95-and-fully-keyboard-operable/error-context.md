# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/tests/e2e/accessibility.spec.ts >> command center remains responsive and fully keyboard operable
- Location: apps/web/tests/e2e/accessibility.spec.ts:15:5

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/command-center", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | import { mockReadyCommandCenter } from "./support";
  3  | 
  4  | test("shell has an accessible main landmark", async ({ page }) => {
  5  |   await page.goto("/");
  6  |   await expect(page.locator("main")).toBeVisible();
  7  |   await page.keyboard.press("Tab");
  8  |   await expect(page.locator(":focus")).toBeVisible();
  9  |   const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
  10 |     .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
  11 |     .map((element) => ({ tag: element.tagName, className: element.className, text: element.textContent?.trim().slice(0, 60), right: Math.round(element.getBoundingClientRect().right) })));
  12 |   expect(overflow).toEqual([]);
  13 | });
  14 | 
  15 | test("command center remains responsive and fully keyboard operable", async ({ page }) => {
  16 |   await mockReadyCommandCenter(page);
  17 |   await page.setViewportSize({ width: 375, height: 812 });
> 18 |   await page.goto("/command-center");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  19 |   const strategies = page.getByRole("button", { name: "Strategies" });
  20 |   await strategies.focus();
  21 |   await expect(strategies).toBeFocused();
  22 |   await page.keyboard.press("Enter");
  23 |   await expect(page.getByRole("heading", { name: "Strategies" })).toBeVisible();
  24 |   const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
  25 |     .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
  26 |     .map((element) => ({ tag: element.tagName, className: element.className, text: element.textContent?.trim().slice(0, 60), right: Math.round(element.getBoundingClientRect().right) })));
  27 |   expect(overflow).toEqual([]);
  28 |   await expect(page.getByRole("navigation", { name: "TraderX workspaces" })).toBeVisible();
  29 | });
  30 | 
  31 | test("primary controls meet contrast and failures expose an accessible recovery message", async ({ page }) => {
  32 |   await mockReadyCommandCenter(page);
  33 |   await page.route("**/api/v1/markets/research", async (route) => route.abort("failed"));
  34 |   await page.goto("/command-center");
  35 |   await page.getByRole("button", { name: "Markets" }).click();
  36 | 
  37 |   const contrast = await page.getByRole("button", { name: "Run Forex research" }).evaluate((element) => {
  38 |     const values = getComputedStyle(element);
  39 |     const parse = (color: string) => (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
  40 |     const luminance = (channels: number[]) => {
  41 |       const normalized = channels.map((channel) => {
  42 |         const value = channel / 255;
  43 |         return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  44 |       });
  45 |       return 0.2126 * normalized[0] + 0.7152 * normalized[1] + 0.0722 * normalized[2];
  46 |     };
  47 |     const foreground = luminance(parse(values.color));
  48 |     const background = luminance(parse(values.backgroundColor));
  49 |     return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
  50 |   });
  51 |   expect(contrast).toBeGreaterThanOrEqual(4.5);
  52 | 
  53 |   await page.getByRole("button", { name: "Run Forex research" }).click();
  54 |   await expect(page.locator(".status-message[role=alert]")).toContainText("could not run market research");
  55 |   await expect(page.getByRole("button", { name: "Run Forex research" })).toBeEnabled();
  56 | });
  57 | 
  58 | test("market automation exposes labelled controls and non-colour evidence states", async ({ page }) => {
  59 |   await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  60 |   await page.setViewportSize({ width: 375, height: 812 });
  61 |   await page.goto("/command-center");
  62 |   await page.getByRole("button", { name: "Markets" }).click();
  63 | 
  64 |   await expect(page.getByLabel("AI provider")).toBeVisible();
  65 |   await expect(page.getByLabel("Model ID")).toBeVisible();
  66 |   await expect(page.getByLabel("Research interval")).toBeVisible();
  67 |   await expect(page.getByLabel("Anchor start")).toBeVisible();
  68 |   await expect(page.getByLabel("Account time zone")).toBeVisible();
  69 |   await page.getByRole("button", { name: "Run all three categories" }).click();
  70 |   const report = page.getByRole("region", { name: "Coordinated market research" });
  71 |   await expect(report).toContainText("BLOCKED");
  72 |   await expect(report).toContainText("analysis unavailable");
  73 |   await report.getByRole("button", { name: "Retry Forex pinned analysis" }).focus();
  74 |   await expect(report.getByRole("button", { name: "Retry Forex pinned analysis" })).toBeFocused();
  75 |   const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
  76 |     .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
  77 |     .map((element) => element.tagName));
  78 |   expect(overflow).toEqual([]);
  79 | });
  80 | 
```