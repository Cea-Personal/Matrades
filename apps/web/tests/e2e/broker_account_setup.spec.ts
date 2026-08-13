import { expect, test } from "@playwright/test";

test("an owner receives a Mac-compatible MT5 EA setup code without any other broker option", async ({ page }) => {
  const account = {
    id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
    name: "Primary evaluation",
    mode: "DEMO",
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
    provider: "MT5_TERMINAL_BRIDGE",
    name: "MT5 Demo-Server 123456",
    mt5_account_login: "123456",
    mt5_server: "Demo-Server",
    status: "DISABLED",
    credential_hint: "configured; verification required",
    enrollment: { agent_id: "4c03fdd7-204c-4054-8a6a-445beaf45d92", code: "mt5-setup-code", expires_at: "2026-08-14T00:00:00Z" }
  };

  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        account,
        risk: { state: "LOCKDOWN", capacity: 0, quality: "UNKNOWN", reason_codes: [] },
        metrics: null,
        onboarding: { account_configured: true, prop_profile_configured: true, risk_policy_configured: true, account_data_verified: false }
      })
    });
  });
  await page.route("**/api/v1/integrations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
    }
  });
  await page.route("**/api/v1/integrations/mt5/enrollments", async (route) => {
    await route.fulfill({ contentType: "application/json", status: 201, body: JSON.stringify(integration) });
  });

  await page.goto("/command-center");
  await expect(page.getByText("OANDA v20", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("radio")).toHaveCount(0);
  await expect(page.getByLabel("Bridge URL", { exact: true })).toHaveCount(0);
  await page.getByLabel("MT5 account login", { exact: true }).fill("123456");
  await page.getByLabel("Broker server", { exact: true }).fill("Demo-Server");
  await page.getByRole("button", { name: "Create MT5 setup code" }).click();
  await expect(page.getByRole("heading", { name: "Install this in your MT5 terminal" })).toBeVisible();
  await expect(page.getByText("This setup code is for MT5 account 123456 on Demo-Server.")).toBeVisible();
  await expect(page.getByText("mt5-setup-code", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download the TraderX Read-only Bridge EA" })).toHaveAttribute("href", "/mt5-bridge/TraderXReadOnlyBridge.mq5");
  const eaDownload = await page.request.get("/mt5-bridge/TraderXReadOnlyBridge.mq5");
  expect(eaDownload.status()).toBe(200);
  expect(await eaDownload.text()).toContain("TraderXReadOnlyBridge");
  await expect(page.getByText("Tools → Options → Expert Advisors")).toBeVisible();
  await expect(page.getByText("https://127.0.0.1:3000", { exact: true })).toHaveCount(2);
  await expect(page.getByText("No bridge URL, identity, or bridge credential is required.")).toBeVisible();
});

test("an owner renews the setup code for an existing MT5 account without creating a duplicate", async ({ page }) => {
  const account = {
    id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
    name: "Primary evaluation",
    mode: "DEMO",
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
    provider: "MT5_TERMINAL_BRIDGE",
    name: "MT5 Demo-Server 123456",
    mt5_account_login: "123456",
    mt5_server: "Demo-Server",
    status: "DISABLED",
    credential_hint: "configured; verification required"
  };
  const renewed = {
    ...integration,
    enrollment: { agent_id: "4c03fdd7-204c-4054-8a6a-445beaf45d92", code: "renewed-mt5-setup-code", expires_at: "2026-08-14T00:00:00Z" }
  };

  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        account,
        risk: { state: "LOCKDOWN", capacity: 0, quality: "UNKNOWN", reason_codes: [] },
        metrics: null,
        onboarding: { account_configured: true, prop_profile_configured: true, risk_policy_configured: true, account_data_verified: false }
      })
    });
  });
  await page.route("**/api/v1/integrations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([integration]) });
    }
  });
  await page.route(`**/api/v1/integrations/${integration.id}/mt5/enrollment`, async (route) => {
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({ contentType: "application/json", status: 201, body: JSON.stringify(renewed) });
  });

  await page.goto("/command-center");
  await expect(page.getByRole("heading", { name: "MT5 account 123456" })).toBeVisible();
  await expect(page.getByText("Broker server:", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create MT5 setup code" })).toHaveCount(0);
  await page.getByRole("button", { name: "Create setup code for this account" }).click();
  await expect(page.getByText("renewed-mt5-setup-code", { exact: true })).toBeVisible();
  await expect(page.getByText("A new MT5 setup code is ready. Any earlier bridge credential was revoked.")).toBeVisible();
});

test("an owner explicitly confirms removal of an MT5 account", async ({ page }) => {
  const account = {
    id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
    name: "Primary evaluation",
    mode: "DEMO",
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
    provider: "MT5_TERMINAL_BRIDGE",
    name: "MT5 Demo-Server 123456",
    mt5_account_login: "123456",
    mt5_server: "Demo-Server",
    status: "DISABLED",
    credential_hint: "configured; verification required"
  };
  let removed = false;

  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        account,
        risk: { state: "LOCKDOWN", capacity: 0, quality: "UNKNOWN", reason_codes: [] },
        metrics: null,
        onboarding: { account_configured: true, prop_profile_configured: true, risk_policy_configured: true, account_data_verified: false }
      })
    });
  });
  await page.route("**/api/v1/integrations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(removed ? [] : [integration]) });
    }
  });
  await page.route(`**/api/v1/integrations/${integration.id}`, async (route) => {
    expect(route.request().method()).toBe("DELETE");
    removed = true;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ integration_id: integration.id, status: "REMOVED", unbound_account_count: 0 }) });
  });

  await page.goto("/command-center");
  await page.getByRole("button", { name: "Remove this MT5 account" }).click();
  await expect(page.getByText("Removing this account revokes its EA credential.")).toBeVisible();
  await page.getByRole("button", { name: "Confirm remove MT5 account 123456" }).click();
  await expect(page.getByText("Removed MT5 account 123456. Its bridge credential was revoked.")).toBeVisible();
  await expect(page.getByText("No broker connection has been saved yet.")).toBeVisible();
});
