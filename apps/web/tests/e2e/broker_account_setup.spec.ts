import { expect, test } from "@playwright/test";

test("an owner can connect, discover, bind, and verify an OANDA practice account", async ({ page }) => {
  const account = {
    id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
    name: "Primary evaluation",
    mode: "LIVE",
    currency: "USD",
    starting_balance: "100000",
    status: "DRAFT",
    version: 1,
    etag: "\"account-1\"",
    prop_profile_configured: true,
    risk_policy_configured: true,
    broker_integration_id: null,
    provider_account_id: null
  };
  const integration = {
    id: "3d15c884-8c25-4f5b-b2f5-764d0a6df313",
    version: 1,
    category: "BROKER",
    provider: "OANDA_V20",
    status: "DISABLED",
    credential_hint: "configured; verification required"
  };
  let integrations: typeof integration[] = [];
  let bound = false;

  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        account: { ...account, broker_integration_id: bound ? integration.id : null, provider_account_id: bound ? "001-001-123" : null },
        risk: { state: bound ? "NORMAL" : "LOCKDOWN", capacity: bound ? 2 : 0, quality: bound ? "VERIFIED" : "UNKNOWN", reason_codes: [] },
        metrics: bound ? { balance: "100000", equity: "100010", realized_pl: "10", floating_pl: "0", observed_at: "2026-08-13T00:00:00Z" } : null,
        onboarding: { account_configured: true, prop_profile_configured: true, risk_policy_configured: true, account_data_verified: bound }
      })
    });
  });
  await page.route("**/api/v1/integrations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(integrations) });
      return;
    }
    integrations = [integration];
    await route.fulfill({ contentType: "application/json", status: 201, body: JSON.stringify(integration) });
  });
  await page.route(`**/api/v1/integrations/${integration.id}/test`, async (route) => {
    await route.fulfill({ contentType: "application/json", status: 202, body: JSON.stringify({ id: "job-1", version: 1, type: "BROKER_CONNECTION_TEST", state: "COMPLETED", progress: {} }) });
  });
  await page.route(`**/api/v1/integrations/${integration.id}/accounts`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([{ provider_account_id: "001-001-123", provider: "OANDA_V20", display_name: "Practice", currency: "USD", account_mode: "PRACTICE", verification_status: "VERIFIED" }])
    });
  });
  await page.route(`**/api/v1/integrations/${integration.id}/accounts/001-001-123/bind`, async (route) => {
    bound = true;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "BLOCKED", verification_required: true }) });
  });
  await page.route(`**/api/v1/integrations/${integration.id}/sync`, async (route) => {
    await route.fulfill({ contentType: "application/json", status: 202, body: JSON.stringify({ status: "VERIFIED" }) });
  });

  await page.goto("/command-center");
  await expect(page.getByRole("heading", { name: "Connect verified account data" })).toBeVisible();
  await page.getByLabel("Personal Access Token", { exact: true }).fill("practice-token-never-rendered");
  await page.getByRole("button", { name: "Save read-only connection" }).click();
  await expect(page.getByText("Connection saved. Test it to discover the account that TraderX may verify.")).toBeVisible();
  await page.getByRole("button", { name: "Test & discover accounts" }).click();
  await expect(page.getByText("Practice", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Bind this account" }).click();
  await expect(page.getByRole("button", { name: "Verify account data" })).toBeVisible();
  await page.getByRole("button", { name: "Verify account data" }).click();
  await expect(page.getByText("Verified broker snapshot recorded. TraderX recalculated the risk state from current account truth.")).toBeVisible();
});
