import { expect, test } from "@playwright/test";

test("unauthenticated visitors see the TraderX authentication entry routes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TraderX" })).toBeVisible();
  await expect(page.getByText("Authenticate to access the Command Center.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  await expect(page.getByRole("link", { name: "Set up the initial owner" })).toHaveAttribute("href", "/setup");
});

test("authentication flows have deep-linkable pages without operational content", async ({ page }) => {
  await page.goto("/sign-in");
  await expect(page.getByRole("form", { name: "TraderX sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Reset your password" })).toHaveAttribute("href", "/password-reset");

  await page.goto("/password-reset");
  await expect(page.getByRole("form", { name: "Request password reset" })).toBeVisible();
  await expect(page.getByRole("form", { name: "Complete password reset" })).toBeVisible();
  await expect(page.getByText("Command Center")).not.toBeVisible();
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
