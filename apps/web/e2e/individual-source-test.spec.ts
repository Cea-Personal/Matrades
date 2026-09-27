import { expect, test } from "@playwright/test";

test("configured data source Test affects only its own row and sends one targeted request", async ({ page }) => {
  const requests: string[] = [];
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const sources = ["Crypto exchange", "Forex feed"].map((name, index) => ({
    id: `source-${index}`, name, provider: index ? "TWELVE_DATA" : "COINBASE",
    health: "UNTESTED", state: "ACTIVE", active: true, capabilities: [],
    updated_at: "2026-09-27T10:00:00Z",
  }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/events") return route.fulfill({ contentType: "text/event-stream", body: ": connected\n\n" });
    if (route.request().method() === "POST" && path.endsWith("/test")) {
      requests.push(path);
      await pending;
      sources[0] = { ...sources[0], health: "HEALTHY" };
      return route.fulfill({ json: sources[0] });
    }
    if (path === "/auth/me") return route.fulfill({ json: {
      id: "user", owner_id: "owner", email: "test@example.com", email_verified: true,
      mfa_enabled: true, role: "OWNER",
    } });
    if (path === "/knowledge/youtube/schedule") return route.fulfill({ json: {
      configured: false, enabled: false, run_at: "05:00", timezone: "UTC",
      weekdays: [], next_run_at: null, query: "trading strategy", limit: 5,
      languages: ["en"], category: "trading",
    } });
    return route.fulfill({ json: path === "/configuration/connections" ? sources : [] });
  });
  try {
    await page.goto("/connections");
    const primary = page.getByRole("row").filter({ has: page.getByText("Crypto exchange", { exact: true }) });
    const secondary = page.getByRole("row").filter({ has: page.getByText("Forex feed", { exact: true }) });
    await primary.getByRole("button", { name: "Test", exact: true }).click();
    await expect(primary.getByRole("button", { name: "Testing…" })).toBeDisabled();
    await expect(secondary.getByRole("button", { name: "Test", exact: true })).toBeEnabled();
    await expect.poll(() => requests).toEqual(["/configuration/connections/source-0/test"]);
    release();
    await expect(primary.getByRole("button", { name: "Test", exact: true })).toBeEnabled();
    await expect(primary.getByRole("status")).toHaveText("Crypto exchange is HEALTHY.");
    await expect(secondary.getByRole("status")).toHaveCount(0);
    expect(requests).toEqual(["/configuration/connections/source-0/test"]);
  } finally {
    release();
  }
});
