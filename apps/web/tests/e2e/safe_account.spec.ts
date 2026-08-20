import { expect, test } from "@playwright/test";

test("unauthenticated visitors see the TraderX authentication entry routes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TraderX" })).toBeVisible();
  await expect(page.getByText("Authenticate to access the Command Center.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  await expect(page.getByRole("link", { name: "Set up the initial owner" })).toHaveAttribute("href", "/setup");
});

test("authentication flows have deep-linkable pages without operational content", async ({ page }) => {
  await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: false }) });
  });
  await page.goto("/sign-in");
  await expect(page.getByRole("form", { name: "TraderX sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Reset your password" })).toHaveAttribute("href", "/password-reset");

  await page.goto("/password-reset");
  await expect(page.getByRole("form", { name: "Request password reset" })).toBeVisible();
  await expect(page.getByRole("form", { name: "Complete password reset" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Command Center" })).not.toBeVisible();
});

test("first-owner signup presents a complete, usable form", async ({ page }) => {
  await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  });

  await page.goto("/setup");
  await expect(page.getByRole("heading", { name: "Set up the initial owner" })).toBeVisible();
  await expect(page.getByRole("form", { name: "Initial owner setup" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
  await expect(page.getByText("Use a unique passphrase with at least 12 characters.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create owner account" })).toBeVisible();
});

test("first-owner signup advances directly to authenticator enrollment", async ({ page }) => {
  await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  });
  await page.route("**/api/v1/auth/bootstrap", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "MFA_ENROLLMENT_REQUIRED" }), status: 201 });
  });
  await page.route("**/api/v1/auth/mfa/enroll", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ provisioning_uri: "otpauth://totp/TraderX:owner%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=TraderX" })
    });
  });

  await page.goto("/setup");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-long-unique-passphrase");
  await page.getByLabel("Confirm password").fill("a-long-unique-passphrase");
  await page.getByRole("button", { name: "Create owner account" }).click();

  await expect(page).toHaveURL(/\/mfa\/enroll$/);
  await expect(page.getByRole("heading", { name: "Set up your authenticator" })).toBeVisible();
  await expect(page.getByLabel("Authenticator setup key")).toContainText("JBSWY3DPEHPK3PXP");
});

test("Command Center gives a new owner a safe account-configuration path", async ({ page }) => {
  let accountCreated = false;
  const noAccount = {
    account: null,
    risk: { state: "LOCKDOWN", capacity: 0, quality: "UNKNOWN", reason_codes: ["NO_PRIMARY_ACCOUNT"] },
    metrics: null,
    onboarding: {
      account_configured: false,
      prop_profile_configured: false,
      risk_policy_configured: false,
      account_data_verified: false
    },
    research_connection_progress: [
      { provider: "CME_GROUP", label: "CME Group", required: true, complete: false },
      { provider: "CBOE_FX_SPOT", label: "Cboe FX Spot", required: false, complete: false },
      { provider: "COINBASE_EXCHANGE", label: "Coinbase Exchange", required: true, complete: false },
      { provider: "LITELLM_PROXY", label: "LiteLLM Gateway", required: false, complete: false }
    ],
    workspace_prerequisites: [
      { label: "Active market selection", target: "markets", required: true, complete: false, purpose: "Strategies" },
      { label: "Validated strategy", target: "strategies", required: true, complete: false, purpose: "Paper trading" },
      { label: "Paper-trading evidence", target: "paper", required: true, complete: false, purpose: "live approval" },
      { label: "Live-approved strategy", target: "opportunities", required: true, complete: false, purpose: "Opportunities" },
      { label: "Open broker position", target: "monitoring", required: false, complete: false, purpose: "Trade monitoring" }
    ]
  };
  const account = {
    id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
    name: "Primary evaluation",
    mode: "LIVE",
    currency: "USD",
    starting_balance: "100000",
    status: "DRAFT",
    version: 1,
    etag: "\"account-1\"",
    prop_profile_configured: false,
    risk_policy_configured: false
  };

  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(accountCreated ? { ...noAccount, account, onboarding: { ...noAccount.onboarding, account_configured: true }, risk: { ...noAccount.risk, reason_codes: ["NO_VERIFIED_ACCOUNT_SNAPSHOT"] } } : noAccount)
    });
  });
  await page.route("**/api/v1/accounts", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    accountCreated = true;
    await route.fulfill({ contentType: "application/json", status: 201, body: JSON.stringify(account) });
  });

  await page.goto("/command-center");
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  const activationSidebar = page.getByRole("complementary", { name: "Safe activation checklist" });
  await expect(activationSidebar).toBeVisible();
  await expect(activationSidebar.getByText("Initial setup")).toBeVisible();
  await expect(activationSidebar.getByText("Account identity")).toBeVisible();
  await expect(activationSidebar.getByText("External loss rules")).toBeVisible();
  await expect(activationSidebar.getByText("Internal guardrails")).toBeVisible();
  await expect(activationSidebar.getByText("Verified account data")).toBeVisible();
  await expect(activationSidebar.getByText("Coinbase Exchange connection")).toBeVisible();
  await expect(activationSidebar.getByText("Required · not connected")).toHaveCount(2);
  await expect(activationSidebar.getByText("Active market selection")).toBeVisible();
  await expect(activationSidebar.getByText("Validated strategy")).toBeVisible();
  await expect(activationSidebar.getByText("Live-approved strategy")).toBeVisible();
  await expect(page.locator(".readiness-card")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "New recommendations are blocked" })).toBeVisible();
  await expect(page.getByRole("form", { name: "Primary account setup" })).toBeVisible();
  await page.getByLabel("Account name").fill("Primary evaluation");
  await page.getByLabel("Starting balance").fill("100000");
  await page.getByRole("button", { name: "Record account identity" }).click();
  await expect(page.getByRole("heading", { name: "Record external loss rules" })).toBeVisible();
});
