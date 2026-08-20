import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("shell has an accessible main landmark", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
    .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
    .map((element) => ({ tag: element.tagName, className: element.className, text: element.textContent?.trim().slice(0, 60), right: Math.round(element.getBoundingClientRect().right) })));
  expect(overflow).toEqual([]);
});

test("command center remains responsive and fully keyboard operable", async ({ page }) => {
  await mockReadyCommandCenter(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/command-center");
  const strategies = page.getByRole("button", { name: "Strategies" });
  await strategies.focus();
  await expect(strategies).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Strategies" })).toBeVisible();
  const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
    .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
    .map((element) => ({ tag: element.tagName, className: element.className, text: element.textContent?.trim().slice(0, 60), right: Math.round(element.getBoundingClientRect().right) })));
  expect(overflow).toEqual([]);
  await expect(page.getByRole("navigation", { name: "TraderX workspaces" })).toBeVisible();
});

test("primary controls meet contrast and failures expose an accessible recovery message", async ({ page }) => {
  await mockReadyCommandCenter(page);
  await page.route("**/api/v1/markets/research", async (route) => route.abort("failed"));
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Markets" }).click();

  const contrast = await page.getByRole("button", { name: "Run Forex research" }).evaluate((element) => {
    const values = getComputedStyle(element);
    const parse = (color: string) => (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
    const luminance = (channels: number[]) => {
      const normalized = channels.map((channel) => {
        const value = channel / 255;
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * normalized[0] + 0.7152 * normalized[1] + 0.0722 * normalized[2];
    };
    const foreground = luminance(parse(values.color));
    const background = luminance(parse(values.backgroundColor));
    return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
  });
  expect(contrast).toBeGreaterThanOrEqual(4.5);

  await page.getByRole("button", { name: "Run Forex research" }).click();
  await expect(page.locator(".status-message[role=alert]")).toContainText("could not run market research");
  await expect(page.getByRole("button", { name: "Run Forex research" })).toBeEnabled();
});

test("market automation exposes labelled controls and non-colour evidence states", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Markets" }).click();

  await expect(page.getByLabel("Global research model")).toBeVisible();
  await expect(page.getByLabel("Research interval")).toBeVisible();
  await expect(page.getByLabel("Anchor start")).toBeVisible();
  await expect(page.getByLabel("Account time zone")).toBeVisible();
  await page.getByRole("button", { name: "Run all three categories" }).click();
  const report = page.getByRole("region", { name: "Coordinated market research" });
  await expect(report).toContainText("BLOCKED");
  await expect(report).toContainText("analysis unavailable");
  await report.getByRole("button", { name: "Retry Forex pinned analysis" }).focus();
  await expect(report.getByRole("button", { name: "Retry Forex pinned analysis" })).toBeFocused();
  const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
    .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
    .map((element) => element.tagName));
  expect(overflow).toEqual([]);
});
