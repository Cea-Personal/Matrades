import { expect, test, type Page } from "@playwright/test";

async function mockWorkspace(page: Page) {
  const writes: string[] = [];
  const record = (id: string, fields: Record<string, unknown> = {}) => ({ id, owner_id: "owner", version: 1, state: "ACTIVE", created_at: "2026-09-27T10:00:00Z", updated_at: "2026-09-27T10:00:00Z", ...fields });
  const accounts = [record("account-a", { name: "Demo account", currency: "USD", starting_balance: "10000", kind: "DEMO" }), record("account-b", { name: "Second account", currency: "USD", starting_balance: "10000", kind: "DEMO" })];
  const symbols = ["EUR/USD", "XAUUSD", "BTC-USD", "AAPL"];
  const schedule = { enabled: false, run_at: "09:00", timezone: "UTC", weekdays: [0, 1, 2, 3, 4], configured: false, next_run_at: null };
  const connections = Array.from({ length: 8 }, (_, index) => record(`connection-${index}`, { name: `Data source ${index}`, provider: "TWELVE_DATA", health: "HEALTHY", capabilities: ["CANDLES", "QUOTE"] }));
  const plans = Array.from({ length: 7 }, (_, index) => record(`plan-${index}`, { instrument: symbols[index % 4], state: "VALIDATED", risk: { decision: "ALLOW" } }));
  const active = Array.from({ length: 7 }, (_, index) => record(`trade-${index}`, { instrument: symbols[index % 4], broker_position: { instrument: symbols[index % 4], direction: "LONG", pnl: "0", stop_loss: "1.0" } }));
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    if (route.request().method() !== "GET") writes.push(path);
    if (path === "/events") return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": connected\n\n" });
    const account = url.searchParams.get("account_id") ?? path.match(/accounts\/([^/]+)/)?.[1] ?? "account-a";
    const responses: Record<string, unknown> = {
      "/auth/me": { id: "user", owner_id: "owner", email: "trader@example.com", email_verified: true, mfa_enabled: true, role: "OWNER" },
      "/configuration/accounts": accounts,
      "/configuration/connections": connections,
      "/configuration/effective-limits": { effective: { MAX_DAILY_LOSS: { value: "5", unit: "percent", source: "guardrail", version: 1 } } },
      "/automation/operations": { trade_plans: plans, execution_commands: [], active_trades: active, execution_mode: "AUTONOMOUS" },
      "/automation/trade-plans": plans,
      "/operations/health": { state: "HEALTHY", components: [{ component: "database", state: "HEALTHY", fresh: true }, { component: "agent-worker", state: "UNAVAILABLE", fresh: false }] },
      "/operations/performance": { groups: {} },
      "/research-runs": [record("current-cycle", { account_id: account, state: "COMPLETED", lane_results: [], ranked_candidates: [] })],
      "/research/runs": [],
      "/research/artifacts": Array.from({ length: 7 }, (_, index) => ({ run_id: `${account}-run-${index}`, account_id: account, state: "COMPLETED", completed_at: `2026-09-${String(27 - index).padStart(2, "0")}T10:00:00Z`, relative_path: `${account}/research-${index}.json`, checksum: "1234567890abcdef" })),
      "/strategies/research-context": { ready: true, market_research_run_id: "current-cycle", market_research_state: "COMPLETED", selections: symbols.map((instrument, index) => ({ instrument, category: "CFD", ready: true, market_selection_id: `selection-${index}`, historical_provider: "MT5_BRIDGE", market_observed_at: "2026-09-27T10:00:00Z" })) },
      "/strategies": [],
      "/agents/status": { codex_worker_heartbeat: false, agents: [] },
      "/agents/runtime-settings": { codex_enabled: true, litellm_enabled: false, litellm_url: "http://localhost:4000", default_codex_model: "configured-model", litellm_api_key_configured: false },
      "/knowledge/health": { state: "HEALTHY", active_sources: 8, indexed_segments: 40, pgvector_available: true },
      "/knowledge/sources": Array.from({ length: 8 }, (_, index) => record(`source-${index}`, { name: `Knowledge ${index}`, category: "trading", source_kind: "DOCUMENT", generation: 1, content_hash: "1234567890", segment_count: 5 })),
      "/knowledge/embedding-configuration": { configured: false, provider: "OPENAI", connection_id: null, model: "text-embedding-3-small", dimensions: 1536 },
      "/knowledge/reranking-configuration": { configured: false, connection_id: null, model: "rerank-v3.5", candidate_limit: 20, verified_at: null },
      "/knowledge/youtube/schedule": { ...schedule, query: "trading strategy", limit: 3, languages: ["en"], category: "trading" },
      "/operations/notifications/preferences": { in_app: true, browser_push: false, email: false, telegram: false, pushover: false, urgent_only_external: true },
      "/extras/overview": { folders: [{ id: "market-research", label: "Market research", description: "Completed cycles", count: 7 }], items: { "market-research": Array.from({ length: 7 }, (_, index) => ({ id: `extra-${index}`, state: "COMPLETED", name: `Archived cycle ${index}`, completed_at: `2026-09-${String(27 - index).padStart(2, "0")}T10:00:00Z`, summary: { instrument: "EUR/USD" } })) } },
    };
    let data = responses[path] ?? [];
    if (path.endsWith("/research-matrix")) data = { account_id: account, version: 1, lanes: ["FOREX", "METALS", "CRYPTOCURRENCY", "STOCKS"].map(asset_class => ({ asset_class, instrument_type: "CFD", enabled: true })) };
    if (path.endsWith("/research-schedule") || path.endsWith("/forex-factory-schedule")) data = { ...schedule, account_id: account };
    if (path.endsWith("/strategy-automation")) data = { account_id: account, enabled: false, backtest_lookback_days: 90, paper_duration_days: 30, max_paper_attempts: 1, spread: "0.0001", commission: "0", slippage: "0.00005" };
    if (path.startsWith("/automation/kill-switch/")) data = { active: false, safety_epoch: 1, reason: "" };
    if (path.startsWith("/automation/permissions/")) data = { account_id: account, version: 1, reason: "", new_entry: false, order_cancellation: false, stop_loss_create_or_modify: false, take_profit_create_or_modify: false, partial_close: false, full_exit: false };
    if (path.startsWith("/operations/journal/")) data = { events: [], trade: {} };
    if (path.endsWith("/chart")) data = { candles: [], overlays: [], freshness: "STALE", mapping_status: "UNMAPPED" };
    return route.fulfill({ status: 200, json: data });
  });
  return writes;
}

test("research shows three recent records and resets the history when changing accounts", async ({ page }, testInfo) => {
  const writes = await mockWorkspace(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "Autonomous market research" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Trading account", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Per-account research cycle" })).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("research-desktop.png"), fullPage: true });
  await page.getByRole("tab", { name: "Research history" }).click();
  const panel = page.getByRole("tabpanel", { name: "Research history" });
  await expect(panel.getByRole("listitem")).toHaveCount(3);
  await expect(panel.getByText("account-a/research-0.json")).toBeVisible();
  await page.getByRole("button", { name: "Load more market research records" }).click();
  await expect(panel.getByRole("listitem")).toHaveCount(6);
  await page.getByRole("combobox", { name: "Trading account", exact: true }).selectOption("account-b");
  await expect(panel.getByRole("listitem")).toHaveCount(3);
  await expect(panel.getByText("account-b/research-0.json")).toBeVisible();
  await expect(panel.getByText("account-a/research-0.json")).toHaveCount(0);
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await page.getByRole("textbox", { name: "Timezone", exact: true }).fill("Africa/Kigali");
  await page.getByRole("tab", { name: "Latest cycle" }).click();
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Timezone", exact: true })).toHaveValue("Africa/Kigali");
  expect(writes).toEqual([]);
});

test("connection and knowledge forms remain available and preserve unsaved drafts", async ({ page }, testInfo) => {
  const writes = await mockWorkspace(page);
  await page.goto("/connections");
  await expect(page.getByRole("heading", { name: "Configured data sources" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "1. Store a credential" })).not.toBeVisible();
  await page.getByText("Add a connection or credential", { exact: true }).click();
  await page.getByRole("textbox", { name: "Connection name", exact: true }).fill("Unsaved connection");
  await page.getByRole("tab", { name: "Account bindings" }).click();
  await page.getByRole("tab", { name: "Data sources", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Connection name", exact: true })).toHaveValue("Unsaved connection");
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Owner-scoped sources" })).toBeVisible();
  await page.getByText("Add text or upload a document", { exact: true }).click();
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Unsaved research note");
  await page.getByRole("tab", { name: "Search & assistant" }).click();
  await expect(page.getByRole("heading", { name: "Audited hybrid search" })).toBeVisible();
  await page.getByRole("tab", { name: "Sources", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Unsaved research note");
  await page.getByText("Add text or upload a document", { exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("knowledge-desktop.png"), fullPage: true });
  expect(writes).toEqual([]);
});

test("trade desk keeps every active position visible while collapsing charts and history", async ({ page }) => {
  const writes = await mockWorkspace(page);
  await page.goto("/trading");
  await expect(page.getByRole("table").first().getByRole("row")).toHaveCount(8);
  await expect(page.locator(".workspace-disclosure[open]")).toHaveCount(0);
  await expect(page.getByText("Showing 3 of 7 trade plans")).toBeVisible();
  await page.getByRole("button", { name: "Load more trade plans" }).click();
  await expect(page.getByText("Showing 6 of 7 trade plans")).toBeVisible();
  expect(writes).toEqual([]);
});

test("every workspace and each tab fits desktop and mobile without rendering errors", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const writes = await mockWorkspace(page);
  for (const path of ["/", "/research", "/strategies", "/connections", "/knowledge", "/configuration", "/agents", "/operations", "/extras", "/trading"]) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (path === "/strategies") await expect(page.locator("strong").filter({ hasText: /^AAPL · CFD$/ })).toBeVisible();
    if (path === "/operations") await expect(page.getByText("agent-worker", { exact: true })).toBeVisible();
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${path} should fit ${width}px` }).toBe(true);
    }
    for (const tab of await page.getByRole("tab").all()) {
      await tab.click();
      await expect(page.getByRole("tabpanel")).toHaveCount(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${path}: ${await tab.textContent()}`).toBe(true);
    }
    if (path === "/strategies" || path === "/operations") await page.screenshot({ path: testInfo.outputPath(`${path.slice(1)}-mobile.png`), fullPage: true });
  }
  expect(errors).toEqual([]);
  expect(writes).toEqual([]);
});
