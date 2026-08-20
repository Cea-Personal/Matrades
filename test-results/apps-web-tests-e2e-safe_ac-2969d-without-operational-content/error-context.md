# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/tests/e2e/safe_account.spec.ts >> authentication flows have deep-linkable pages without operational content
- Location: apps/web/tests/e2e/safe_account.spec.ts:11:5

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/sign-in", waiting until "load"

```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   | 
  3   | test("unauthenticated visitors see the TraderX authentication entry routes", async ({ page }) => {
  4   |   await page.goto("/");
  5   |   await expect(page.getByRole("heading", { name: "TraderX" })).toBeVisible();
  6   |   await expect(page.getByText("Authenticate to access the Command Center.")).toBeVisible();
  7   |   await expect(page.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  8   |   await expect(page.getByRole("link", { name: "Set up the initial owner" })).toHaveAttribute("href", "/setup");
  9   | });
  10  | 
  11  | test("authentication flows have deep-linkable pages without operational content", async ({ page }) => {
  12  |   await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
  13  |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: false }) });
  14  |   });
> 15  |   await page.goto("/sign-in");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  16  |   await expect(page.getByRole("form", { name: "TraderX sign in" })).toBeVisible();
  17  |   await expect(page.getByRole("link", { name: "Reset your password" })).toHaveAttribute("href", "/password-reset");
  18  | 
  19  |   await page.goto("/password-reset");
  20  |   await expect(page.getByRole("form", { name: "Request password reset" })).toBeVisible();
  21  |   await expect(page.getByRole("form", { name: "Complete password reset" })).toBeVisible();
  22  |   await expect(page.getByRole("heading", { name: "Command Center" })).not.toBeVisible();
  23  | });
  24  | 
  25  | test("first-owner signup presents a complete, usable form", async ({ page }) => {
  26  |   await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
  27  |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  28  |   });
  29  | 
  30  |   await page.goto("/setup");
  31  |   await expect(page.getByRole("heading", { name: "Set up the initial owner" })).toBeVisible();
  32  |   await expect(page.getByRole("form", { name: "Initial owner setup" })).toBeVisible();
  33  |   await expect(page.getByLabel("Email")).toBeVisible();
  34  |   await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
  35  |   await expect(page.getByText("Use a unique passphrase with at least 12 characters.")).toBeVisible();
  36  |   await expect(page.getByRole("button", { name: "Create owner account" })).toBeVisible();
  37  | });
  38  | 
  39  | test("first-owner signup advances directly to authenticator enrollment", async ({ page }) => {
  40  |   await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
  41  |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  42  |   });
  43  |   await page.route("**/api/v1/auth/bootstrap", async (route) => {
  44  |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "MFA_ENROLLMENT_REQUIRED" }), status: 201 });
  45  |   });
  46  |   await page.route("**/api/v1/auth/mfa/enroll", async (route) => {
  47  |     await route.fulfill({
  48  |       contentType: "application/json",
  49  |       body: JSON.stringify({ provisioning_uri: "otpauth://totp/TraderX:owner%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=TraderX" })
  50  |     });
  51  |   });
  52  | 
  53  |   await page.goto("/setup");
  54  |   await page.getByLabel("Email").fill("owner@example.com");
  55  |   await page.getByLabel("Password", { exact: true }).fill("a-long-unique-passphrase");
  56  |   await page.getByLabel("Confirm password").fill("a-long-unique-passphrase");
  57  |   await page.getByRole("button", { name: "Create owner account" }).click();
  58  | 
  59  |   await expect(page).toHaveURL(/\/mfa\/enroll$/);
  60  |   await expect(page.getByRole("heading", { name: "Set up your authenticator" })).toBeVisible();
  61  |   await expect(page.getByLabel("Authenticator setup key")).toContainText("JBSWY3DPEHPK3PXP");
  62  | });
  63  | 
  64  | test("Command Center gives a new owner a safe account-configuration path", async ({ page }) => {
  65  |   let accountCreated = false;
  66  |   const noAccount = {
  67  |     account: null,
  68  |     risk: { state: "LOCKDOWN", capacity: 0, quality: "UNKNOWN", reason_codes: ["NO_PRIMARY_ACCOUNT"] },
  69  |     metrics: null,
  70  |     onboarding: {
  71  |       account_configured: false,
  72  |       prop_profile_configured: false,
  73  |       risk_policy_configured: false,
  74  |       account_data_verified: false
  75  |     }
  76  |   };
  77  |   const account = {
  78  |     id: "93c4d259-3341-4d26-91d5-7891e3f1b340",
  79  |     name: "Primary evaluation",
  80  |     mode: "LIVE",
  81  |     currency: "USD",
  82  |     starting_balance: "100000",
  83  |     status: "DRAFT",
  84  |     version: 1,
  85  |     etag: "\"account-1\"",
  86  |     prop_profile_configured: false,
  87  |     risk_policy_configured: false
  88  |   };
  89  | 
  90  |   await page.route("**/api/v1/dashboard", async (route) => {
  91  |     await route.fulfill({
  92  |       contentType: "application/json",
  93  |       body: JSON.stringify(accountCreated ? { ...noAccount, account, onboarding: { ...noAccount.onboarding, account_configured: true }, risk: { ...noAccount.risk, reason_codes: ["NO_VERIFIED_ACCOUNT_SNAPSHOT"] } } : noAccount)
  94  |     });
  95  |   });
  96  |   await page.route("**/api/v1/accounts", async (route) => {
  97  |     if (route.request().method() !== "POST") return route.fallback();
  98  |     accountCreated = true;
  99  |     await route.fulfill({ contentType: "application/json", status: 201, body: JSON.stringify(account) });
  100 |   });
  101 | 
  102 |   await page.goto("/command-center");
  103 |   await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  104 |   const activationSidebar = page.getByRole("complementary", { name: "Safe activation checklist" });
  105 |   await expect(activationSidebar).toBeVisible();
  106 |   await expect(activationSidebar.getByText("Initial setup")).toBeVisible();
  107 |   await expect(activationSidebar.getByText("Account identity")).toBeVisible();
  108 |   await expect(activationSidebar.getByText("External loss rules")).toBeVisible();
  109 |   await expect(activationSidebar.getByText("Internal guardrails")).toBeVisible();
  110 |   await expect(activationSidebar.getByText("Verified account data")).toBeVisible();
  111 |   await expect(page.locator(".readiness-card")).toHaveCount(0);
  112 |   await expect(page.getByRole("heading", { name: "New recommendations are blocked" })).toBeVisible();
  113 |   await expect(page.getByRole("form", { name: "Primary account setup" })).toBeVisible();
  114 |   await page.getByLabel("Account name").fill("Primary evaluation");
  115 |   await page.getByLabel("Starting balance").fill("100000");
```