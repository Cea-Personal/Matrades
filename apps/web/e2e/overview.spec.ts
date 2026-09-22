import { expect, test, type Page } from "@playwright/test";

async function mockOverview(page: Page, mode: "populated" | "empty" | "unavailable" = "populated") {
  const now = new Date();
  const ago = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();
  const resource = (id: string, fields: Record<string, unknown> = {}) => ({ id, owner_id: "owner", state: "ACTIVE", created_at: ago(120), updated_at: ago(120), ...fields });
  const symbols = [["XAUUSD", "METALS"], ["EURUSD", "FOREX"], ["BTCUSD", "CRYPTOCURRENCY"]];
  const accounts = mode === "empty" ? [] : [resource("account-1", { name: "Primary trading account", currency: "USD", starting_balance: "200000" }), resource("account-2", { name: "Euro account", currency: "EUR", starting_balance: "10000" })];
  const runs = mode === "empty" ? [] : [resource("run-1", { account_id: "account-1", state: "COMPLETED", lane_results: symbols.map(([symbol, asset_class], index) => ({ status: "READY", candidate: { score: 90 - index, listing: { id: symbol, symbol, asset_class } } })) })];
  const drafts = mode === "empty" ? [] : symbols.map(([instrument], index) => resource(`draft-${index}`, { created_at: ago(60 + index), state: "GENERATED", research_basis: { market_research_run_id: "run-1", instrument }, proposed_specification: { name: `${instrument} trend confirmation` }, trade_setup: { status: index === 1 ? "WAIT" : "SIGNAL", expires_at: ago(index === 2 ? 1 : -60) } }));
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    if (path === "/events") return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": connected\n\n" });
    if (mode === "unavailable" && ["/operations/health", "/automation/operations", "/automation/equity-history"].includes(path)) return route.fulfill({ status: 503, json: { detail: "Temporarily unavailable" } });
    const alternate = url.searchParams.get("account_id") === "account-2";
    const series = [190300, 189800, 188000, 190000, 187900, 186500, 184700, 189500, 196700, 192300, 187500, 186100, 182900, 185700, 189432];
    const responses: Record<string, unknown> = {
      "/auth/me": { id: "user", owner_id: "owner", email: "trader@example.com", email_verified: true, mfa_enabled: true, role: "OWNER" },
      "/configuration/accounts": accounts,
      "/automation/operations": { trade_plans: [], execution_commands: [], active_trades: [], execution_mode: "AUTONOMOUS" },
      "/operations/health": { state: "HEALTHY", components: ["database", "codex_app_server", "connection:FF Economic Calendar", "connection:MT5 connection", "connection:Twelve connection", "connection:Coinbase Crypto Connection", "connection:Fred Economic Calendar", "connection:Embeddings Models", "connection:CoinGecko Crypto Connection"].map(component => ({ component, state: "HEALTHY" })) },
      "/research/runs": runs,
      "/strategies": drafts,
      "/configuration/effective-limits": { effective: { MAX_DAILY_LOSS: { value: "8", unit: "percent" } } },
      "/automation/equity-history": { account_id: alternate ? "account-2" : "account-1", currency: alternate ? "EUR" : "USD", points: mode === "empty" ? [] : series.map((value, index) => ({ id: `snapshot-${index}`, observed_at: ago((series.length - index - 1) * 5), equity: String(alternate ? 10500 + index : value), balance: alternate ? "10000" : "190000" })) },
    };
    return route.fulfill({ status: 200, json: responses[path] ?? [] });
  });
}

test("signed-out root redirects to authentication", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "session required" }) }),
  );
  await page.goto("/");
  await expect(page).toHaveURL(/\/auth$/);
  await expect(page.getByRole("heading", { name: "Sign in to Matrades" })).toBeVisible();
});

test("overview displays recorded data, signals and account-specific equity", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1520, height: 1000 });
  await mockOverview(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Autonomous trading command center" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Overview", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("$189,432", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Recorded account equity and balance history" })).toBeVisible();
  await expect(page.getByText("Setup found", { exact: true })).toBeVisible();
  await expect(page.getByText("Watch", { exact: true })).toBeVisible();
  await expect(page.getByText("Stale", { exact: true })).toBeVisible();
  await expect(page.locator(".overview-recent .research-list li")).toHaveCount(4);
  await expect(page.getByRole("link", { name: "View all trade suggestions" })).toHaveAttribute("href", "/strategies");
  await page.screenshot({ path: testInfo.outputPath("overview-desktop.png"), fullPage: true });
  await page.getByRole("combobox", { name: "Equity account" }).selectOption("account-2");
  await expect(page.getByText("€10,514", { exact: true })).toBeVisible();
  await expect(page.getByText("$189,432", { exact: true })).not.toBeVisible();
  await page.getByText("View recorded values").click();
  await expect(page.getByRole("table")).toBeVisible();
});

test("empty overview remains useful and navigation works on mobile", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockOverview(page, "empty");
  await page.goto("/");
  await expect(page.getByText("No trading account yet.")).toBeVisible();
  await expect(page.getByText("No selected pairs yet.")).toBeVisible();
  await expect(page.getByRole("img", { name: "Recorded account equity and balance history" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("overview-mobile.png"), fullPage: true });
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("link", { name: "Trade desk", exact: true }).click();
  await expect(page).toHaveURL(/\/trading$/);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("failed dependencies are not shown as healthy or zero balances", async ({ page }) => {
  await mockOverview(page, "unavailable");
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Health unavailable View dependency status" })).toBeVisible();
  await expect(page.getByText("UNAVAILABLE", { exact: true })).toBeVisible();
  await expect(page.getByText("Data unavailable", { exact: true })).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Account Equity (Recorded)" })).toBeVisible();
  await expect(page.locator(".equity-headline > strong")).toHaveText("—");
});

test("populated panels fit laptop, tablet and mobile widths", async ({ page }) => {
  await mockOverview(page);
  await page.goto("/");
  await expect(page.getByText("$189,432", { exact: true })).toBeVisible();
  for (const width of [1280, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole("heading", { name: "Recent Research", exact: true })).toBeVisible();
  }
});
