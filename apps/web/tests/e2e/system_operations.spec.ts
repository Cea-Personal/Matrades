import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("an owner operates integrations, jobs, notifications, health, and audit from the UI", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedOperations: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Integrations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "MT5 account 5054425064" })).toBeVisible();
  await page.getByRole("button", { name: "Reconnect MT5 bridge" }).click();
  await expect(page.getByText("rotated-operations-setup-code", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("earlier bridge credential was revoked");

  await page.getByRole("button", { name: "Operations" }).click();
  await expect(page.getByRole("heading", { name: "Background jobs" })).toBeVisible();
  await expect(page.getByText("MARKET_RESEARCH")).toBeVisible();
  await page.getByRole("button", { name: "pause" }).click();
  await expect(page.getByText("PAUSED")).toBeVisible();

  await expect(page.getByRole("heading", { name: "Notification inbox and delivery" })).toBeVisible();
  await page.getByLabel("EMAIL").click();
  await expect(page.getByRole("status")).toContainText("EMAIL preference saved");
  await page.getByRole("button", { name: "Test email" }).click();
  await expect(page.getByText("Email channel test")).toBeVisible();

  await expect(page.getByRole("heading", { name: "System health and append-only audit" })).toBeVisible();
  await expect(page.getByText("Overall HEALTHY")).toBeVisible();
  await expect(page.getByText("integration.credential.rotate")).toBeVisible();
  await expect(page.getByText("OWNER", { exact: true })).toBeVisible();
});
