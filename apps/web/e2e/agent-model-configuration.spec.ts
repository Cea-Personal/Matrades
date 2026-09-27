import { expect, test } from "@playwright/test";

test("agent configuration separates native models, explicit overrides and verified history", async ({ page }) => {
  const writes: string[] = [];
  const agents = ["technical_analyst", "critic"].map((logical_id, index) => ({
    logical_id, required: true, runtime: "CODEX_APP_SERVER", profile_id: index ? "custom" : null,
    recommended_model: "native-file-model", recommended_reasoning_effort: "low",
    configured_model: index ? "saved-profile-model" : "native-file-model",
    configured_reasoning_effort: index ? "high" : "low",
    model_source: index ? "profile_override" : "native_agent",
    native_config_file: `.codex/agents/${logical_id}.toml`,
    system_prompt_override: null, user_prompt_override: null, permission_set_version: "v1",
  }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/events") return route.fulfill({ contentType: "text/event-stream", body: ": connected\n\n" });
    if (route.request().method() === "PUT") {
      writes.push(path);
      const body = route.request().postDataJSON();
      expect(body.profile_id).toBeNull();
      expect(body.permission_set_version).toBe("v1");
      agents[1] = { ...agents[1], profile_id: null, configured_model: "native-file-model", configured_reasoning_effort: "low", model_source: "native_agent" };
      return route.fulfill({ json: body });
    }
    const responses: Record<string, unknown> = {
      "/auth/me": { id: "user", owner_id: "owner", email: "test@example.com", email_verified: true, role: "OWNER" },
      "/agents/registry": agents,
      "/agents/profiles": [{ id: "custom", name: "Custom review", runtime: "CODEX_APP_SERVER", model: "saved-profile-model", provider: "openai", fallback_profile_ids: [], capabilities: [], active: true }],
      "/agents/status": { codex_worker_heartbeat: true, codex_auth_mode: "HOST_MOUNTED_AUTH_JSON", agents: [
        { logical_id: "technical_analyst", actual_runtime: "CODEX_APP_SERVER", actual_model: "last-run-model", model_verified: true, execution_id: "verified-execution", last_status: "SUCCEEDED", last_tested_at: "2026-09-27T10:00:00Z", duration_ms: 25 },
        { logical_id: "critic", actual_runtime: "CODEX_APP_SERVER", actual_model: "unverified-legacy-model", model_verified: false, execution_id: "legacy-execution", last_status: "SUCCEEDED" },
      ] },
      "/agents/runtime-settings": { codex_enabled: true, litellm_enabled: false, litellm_url: "http://localhost:4000", default_codex_model: "platform-fallback", litellm_api_key_configured: false },
    };
    return route.fulfill({ json: responses[path] ?? [] });
  });
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Logical agent registry" })).toBeVisible();
  await expect(page.getByText("native-file-model · low", { exact: true })).toBeVisible();
  await expect(page.getByText("last-run-model", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: /^Saved profile override/ })).toBeVisible();
  await expect(page.getByText("Model unverified — retest", { exact: true })).toBeVisible();
  await expect(page.getByText("unverified-legacy-model", { exact: true })).toHaveCount(0);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  const critic = page.getByRole("row").filter({ has: page.getByText("critic", { exact: true }) });
  await critic.getByRole("button", { name: "Configure" }).click();
  await page.getByRole("combobox", { name: "Model profile" }).selectOption("");
  await page.getByRole("button", { name: "Activate configuration" }).click();
  await expect(page.getByRole("cell", { name: /^Saved profile override/ })).toHaveCount(0);
  expect(writes).toEqual(["/agents/critic"]);
});

test("an individual Test button sends only its own request and does not disable other agents", async ({ page }) => {
  const tests: string[] = [];
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const agents = ["technical_analyst", "critic"].map(logical_id => ({
    logical_id, required: true, runtime: "CODEX_APP_SERVER", profile_id: null,
    configured_model: "native-file-model", configured_reasoning_effort: "low",
    system_prompt_override: null, user_prompt_override: null, permission_set_version: "v1",
  }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/events") return route.fulfill({ contentType: "text/event-stream", body: ": connected\n\n" });
    if (route.request().method() === "POST" && path.endsWith("/test")) {
      tests.push(path);
      await pending;
      return route.fulfill({ json: {
        execution: { logical_id: "technical_analyst", status: "SUCCEEDED", actual_runtime: "CODEX_APP_SERVER" },
        result: { summary: "Selected agent only" },
      } });
    }
    const responses: Record<string, unknown> = {
      "/auth/me": { id: "user", owner_id: "owner", email: "test@example.com", email_verified: true, role: "OWNER" },
      "/agents/registry": agents,
      "/agents/profiles": [],
      "/agents/status": { codex_worker_heartbeat: true, codex_auth_mode: "HOST_MOUNTED_AUTH_JSON", agents: [] },
      "/agents/runtime-settings": { codex_enabled: true, litellm_enabled: false, litellm_url: "http://localhost:4000", default_codex_model: "platform-fallback", litellm_api_key_configured: false },
    };
    return route.fulfill({ json: responses[path] ?? [] });
  });
  try {
    await page.goto("/agents");
    const analyst = page.getByRole("row").filter({ has: page.getByText("technical_analyst", { exact: true }) });
    const critic = page.getByRole("row").filter({ has: page.getByText("critic", { exact: true }) });
    await analyst.getByRole("button", { name: "Test", exact: true }).click();
    await expect(analyst.getByRole("button", { name: "Testing…" })).toBeDisabled();
    await expect(critic.getByRole("button", { name: "Test", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Test all logical agents" })).toBeDisabled();
    await expect.poll(() => tests).toEqual(["/agents/technical_analyst/test"]);
    release();
    await expect(analyst.getByRole("button", { name: "Test", exact: true })).toBeEnabled();
    await expect(page.getByText("technical_analyst · SUCCEEDED", { exact: true })).toBeVisible();
    expect(tests).toEqual(["/agents/technical_analyst/test"]);
  } finally {
    release();
  }
});
