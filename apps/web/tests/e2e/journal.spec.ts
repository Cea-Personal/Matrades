import { expect, test } from "@playwright/test";
import { mockReadyCommandCenter } from "./support";

test("journal behavior creates proposals without changing strategy history", async ({ page }) => {
  await mockReadyCommandCenter(page, { seedJournal: true });
  await page.goto("/command-center");
  await page.getByRole("button", { name: "Journal" }).click();
  await expect(page.getByRole("button", { name: "Update from completed activity" })).toBeVisible();
  await page.getByText("Automatic evidence", { exact: true }).click();
  await expect(page.getByText(/PLAN_FOLLOWED/)).toBeVisible();
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Annotate" }).click();
  await page.getByLabel("Behavioral context and review notes").fill("Followed the plan and waited for confirmation");
  await page.getByLabel("Protected screenshot").setInputFiles({ name: "chart.png", mimeType: "image/png", buffer: Buffer.from("chart") });
  await page.getByRole("button", { name: "Append annotation" }).click();
  await page.getByText(/Annotations \(1\)/).click();
  await expect(page.getByText(/Followed the plan/)).toBeVisible();
  await page.getByLabel("Compare by").selectOption("behavior");
  await expect(page.getByText("PLAN_FOLLOWED", { exact: true })).toBeVisible();
  await page.getByLabel("Evidence-linked research hypothesis").fill("Test trend entries after planned pullbacks");
  await page.getByRole("button", { name: /Create proposal from 1 selected entry/ }).click();
  await expect(page.getByRole("status")).toContainText("No strategy or lifecycle state was changed");
});
