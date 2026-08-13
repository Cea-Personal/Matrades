# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/tests/e2e/safe_account.spec.ts >> first-owner signup advances directly to authenticator enrollment
- Location: apps/web/tests/e2e/safe_account.spec.ts:36:5

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/setup", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | test("unauthenticated visitors see the TraderX authentication entry routes", async ({ page }) => {
  4  |   await page.goto("/");
  5  |   await expect(page.getByRole("heading", { name: "TraderX" })).toBeVisible();
  6  |   await expect(page.getByText("Authenticate to access the Command Center.")).toBeVisible();
  7  |   await expect(page.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  8  |   await expect(page.getByRole("link", { name: "Set up the initial owner" })).toHaveAttribute("href", "/setup");
  9  | });
  10 | 
  11 | test("authentication flows have deep-linkable pages without operational content", async ({ page }) => {
  12 |   await page.goto("/sign-in");
  13 |   await expect(page.getByRole("form", { name: "TraderX sign in" })).toBeVisible();
  14 |   await expect(page.getByRole("link", { name: "Reset your password" })).toHaveAttribute("href", "/password-reset");
  15 | 
  16 |   await page.goto("/password-reset");
  17 |   await expect(page.getByRole("form", { name: "Request password reset" })).toBeVisible();
  18 |   await expect(page.getByRole("form", { name: "Complete password reset" })).toBeVisible();
  19 |   await expect(page.getByText("Command Center")).not.toBeVisible();
  20 | });
  21 | 
  22 | test("first-owner signup presents a complete, usable form", async ({ page }) => {
  23 |   await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
  24 |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  25 |   });
  26 | 
  27 |   await page.goto("/setup");
  28 |   await expect(page.getByRole("heading", { name: "Set up the initial owner" })).toBeVisible();
  29 |   await expect(page.getByRole("form", { name: "Initial owner setup" })).toBeVisible();
  30 |   await expect(page.getByLabel("Email")).toBeVisible();
  31 |   await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
  32 |   await expect(page.getByText("Use a unique passphrase with at least 12 characters.")).toBeVisible();
  33 |   await expect(page.getByRole("button", { name: "Create owner account" })).toBeVisible();
  34 | });
  35 | 
  36 | test("first-owner signup advances directly to authenticator enrollment", async ({ page }) => {
  37 |   await page.route("**/api/v1/auth/bootstrap-status", async (route) => {
  38 |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ bootstrap_available: true }) });
  39 |   });
  40 |   await page.route("**/api/v1/auth/bootstrap", async (route) => {
  41 |     await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "MFA_ENROLLMENT_REQUIRED" }), status: 201 });
  42 |   });
  43 |   await page.route("**/api/v1/auth/mfa/enroll", async (route) => {
  44 |     await route.fulfill({
  45 |       contentType: "application/json",
  46 |       body: JSON.stringify({ provisioning_uri: "otpauth://totp/TraderX:owner%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=TraderX" })
  47 |     });
  48 |   });
  49 | 
> 50 |   await page.goto("/setup");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  51 |   await page.getByLabel("Email").fill("owner@example.com");
  52 |   await page.getByLabel("Password", { exact: true }).fill("a-long-unique-passphrase");
  53 |   await page.getByLabel("Confirm password").fill("a-long-unique-passphrase");
  54 |   await page.getByRole("button", { name: "Create owner account" }).click();
  55 | 
  56 |   await expect(page).toHaveURL(/\/mfa\/enroll$/);
  57 |   await expect(page.getByRole("heading", { name: "Set up your authenticator" })).toBeVisible();
  58 |   await expect(page.getByLabel("Authenticator setup key")).toContainText("JBSWY3DPEHPK3PXP");
  59 | });
  60 | 
```