import { expect, test, type Page } from "@playwright/test";

const folders = [
  { id: "market-research", label: "Market research" },
  { id: "strategy-research", label: "Strategy research" },
  { id: "trade-recommendations", label: "Trade recommendations" },
  { id: "generated-code", label: "Generated code" },
  { id: "mt5-bridge-ea", label: "MT5 bridge EA" },
];

async function mockExtras(page: Page) {
  const writes: string[] = [];
  const items = Object.fromEntries(folders.map(folder => [folder.id, Array.from({ length: folder.id === "mt5-bridge-ea" ? 1 : 7 }, (_, index) => ({
    id: `${folder.id}-${index}`, folder: folder.id, name: `${folder.label} record ${index}`,
    state: index === 0 ? "FAILED" : "COMPLETED", completed_at: `2026-09-${String(27 - index).padStart(2, "0")}T10:00:00Z`,
    summary: { instrument: index === 6 ? "XAUUSD" : "EURUSD", category: "CFD", reason: index === 0 ? "Provider unavailable" : null },
    details: { instrument: index === 6 ? "XAUUSD" : "EURUSD", action: "WAIT", retained_evidence: "Full audit record" },
    code: ["generated-code", "mt5-bridge-ea"].includes(folder.id) ? `// Inspectable source ${index}` : undefined,
    language: folder.id === "mt5-bridge-ea" ? "mql5" : "python", artifact_hash: "1234567890abcdef",
    download_path: folder.id === "mt5-bridge-ea" ? "/api/v1/extras/mt5-ea/download" : undefined,
    why: { evidence: ["Historical observations"] },
  }))]));
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (route.request().method() !== "GET") writes.push(path);
    if (path === "/events") return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": connected\n\n" });
    const data = path === "/auth/me" ? { id: "user", owner_id: "owner", email: "trader@example.com", email_verified: true, mfa_enabled: true, role: "OWNER" }
      : path === "/extras/overview" ? { folders: folders.map(folder => ({ ...folder, count: items[folder.id].length, description: `Recorded ${folder.label.toLowerCase()} evidence` })), items } : [];
    return route.fulfill({ status: 200, json: data });
  });
  return writes;
}

test("every Extras folder starts compact, with expandable records and filters", async ({ page }, testInfo) => {
  const writes = await mockExtras(page);
  await page.goto("/extras");
  const nav = page.getByRole("navigation", { name: "Extras folders" });
  for (const folder of folders) {
    await nav.getByRole("link", { name: new RegExp(folder.label) }).click();
    await expect(page).toHaveURL(new RegExp(`folder=${folder.id}$`));
    const archive = page.getByRole("region", { name: `${folder.label} archive` });
    await expect(archive.getByRole("heading", { level: 3 }).first()).toHaveText(`${folder.label} record 0`);
    await expect(archive.getByRole("article")).toHaveCount(folder.id === "mt5-bridge-ea" ? 1 : 3);
    await expect(archive.locator("details[open]")).toHaveCount(0);
    await expect(nav.getByRole("link", { name: new RegExp(folder.label) })).toHaveAttribute("aria-current", "page");
    if (folder.id !== "mt5-bridge-ea") {
      await archive.getByRole("button", { name: "Load more archive records" }).click();
      await expect(archive.getByRole("article")).toHaveCount(6);
      await archive.getByRole("searchbox", { name: "Search this folder" }).fill("XAUUSD");
      await expect(archive.getByRole("article")).toHaveCount(1);
      await expect(archive.getByRole("heading", { name: `${folder.label} record 6` })).toBeVisible();
      await archive.getByRole("button", { name: "Clear filters" }).click();
      await archive.getByRole("combobox", { name: "Record status" }).selectOption("FAILED");
      await expect(archive.getByRole("article")).toHaveCount(1);
      await expect(archive.getByText("Provider unavailable", { exact: true }).first()).toBeVisible();
      await archive.getByRole("button", { name: "Clear filters" }).click();
      await expect(archive.getByRole("article")).toHaveCount(3);
    } else {
      await expect(archive.getByRole("link", { name: "Download .mq5" })).toHaveAttribute("href", /\/api\/v1\/extras\/mt5-ea\/download$/);
      await archive.getByText("View source code", { exact: true }).click();
      await expect(archive.getByLabel(`Source code for ${folder.label} record 0`)).toBeVisible();
      await archive.getByText("View source code", { exact: true }).click();
    }
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${folder.id} at ${width}px`).toBe(true);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await nav.getByRole("link", { name: /Market research/ }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("extras-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath("extras-mobile.png"), fullPage: true });
  expect(writes).toEqual([]);
});

test("folder URLs, sidebar links and browser Back stay in sync", async ({ page }) => {
  const writes = await mockExtras(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/extras?folder=strategy-research");
  const nav = page.getByRole("navigation", { name: "Extras folders" });
  await expect(page.getByRole("region", { name: "Strategy research archive" })).toBeVisible();
  await nav.getByRole("link", { name: /Generated code/ }).click();
  await expect(page.getByRole("region", { name: "Generated code archive" })).toBeVisible();
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Market research", exact: true }).click();
  await expect(page.getByRole("region", { name: "Market research archive" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/folder=generated-code$/);
  await expect(page.getByRole("region", { name: "Generated code archive" })).toBeVisible();
  await page.reload();
  await expect(nav.getByRole("link", { name: /Generated code/ })).toHaveAttribute("aria-current", "page");
  expect(writes).toEqual([]);
});
