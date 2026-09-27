import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { deferred } from "@/test/deferred";
import { AgentConfiguration } from "./AgentConfiguration";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const agents = ["technical_analyst", "critic"].map((logical_id, index) => ({
  logical_id, required: true, runtime: "CODEX_APP_SERVER", profile_id: index ? "custom" : null,
  recommended_model: index ? "native-critic" : "native-analyst",
  recommended_reasoning_effort: "low", configured_model: index ? "saved-model" : "native-analyst",
  configured_reasoning_effort: index ? "high" : "low",
  model_source: index ? "profile_override" : "native_agent",
  native_config_file: `.codex/agents/${logical_id}.toml`,
  system_prompt_override: null, user_prompt_override: null, permission_set_version: "v1",
}));
const status = {
  codex_worker_heartbeat: true, codex_auth_mode: "HOST_MOUNTED_AUTH_JSON",
  agents: [{
    logical_id: "technical_analyst", actual_runtime: "CODEX_APP_SERVER",
    actual_model: "historical-verified-model", model_verified: true,
    orchestrator_model: "observed-orchestrator", last_status: "SUCCEEDED",
    execution_id: "execution-proof", last_tested_at: "2026-09-27T10:00:00Z", duration_ms: 50,
  }, {
    logical_id: "critic", actual_runtime: "CODEX_APP_SERVER", actual_model: "legacy-unverified-model",
    model_verified: false, last_status: "SUCCEEDED", execution_id: "legacy-record",
  }],
};

beforeEach(() => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/agents/registry") return agents;
    if (path === "/agents/profiles") return [{ id: "custom", name: "Custom review", model: "saved-model" }];
    if (path === "/agents/status") return status;
    return {};
  });
});
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AgentConfiguration /></QueryClientProvider>);
  return client;
}

test("shows current native settings separately from verified historical execution and saved overrides", async () => {
  show();
  const row = (await screen.findByText("technical_analyst", { selector: "strong" })).closest("tr")!;
  const cells = within(row);
  expect(cells.getByText("native-analyst · low")).toBeInTheDocument();
  expect(await cells.findByText("historical-verified-model")).toBeInTheDocument();
  expect(cells.getByText("Orchestrator: observed-orchestrator")).toBeInTheDocument();
  expect(cells.getByText("Configured model differs from this historical run")).toBeInTheDocument();
  expect(cells.getByText(".codex/agents/technical_analyst.toml")).toBeInTheDocument();
  expect(screen.getByText("saved-model · high")).toBeInTheDocument();
  expect(screen.getByText("Saved profile override")).toBeInTheDocument();
  expect(screen.getByText("Model unverified — retest")).toBeInTheDocument();
  expect(screen.queryByText("legacy-unverified-model")).not.toBeInTheDocument();
});

test("clearing a saved profile restores native-file selection without changing permission settings", async () => {
  show();
  const row = (await screen.findByText("critic", { selector: "strong" })).closest("tr")!;
  fireEvent.click(within(row).getByRole("button", { name: "Configure" }));
  const select = screen.getByRole("combobox", { name: "Model profile" });
  expect(select).toHaveValue("custom");
  fireEvent.change(select, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Activate configuration" }));
  await waitFor(() => expect(vi.mocked(api).mock.calls.some(([path, options]) => {
    if (path !== "/agents/critic" || options?.method !== "PUT") return false;
    const body = JSON.parse(options.body as string);
    return body.profile_id === null && body.runtime === "CODEX_APP_SERVER" && body.permission_set_version === "v1";
  })).toBe(true));
});

test("refreshed file settings update configuration without rewriting execution history", async () => {
  const client = show();
  await screen.findByText("native-analyst · low");
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/agents/registry") return agents.map(agent => ({ ...agent, configured_model: "edited-native-model" }));
    if (path === "/agents/status") return status;
    return [];
  });
  await client.invalidateQueries({ queryKey: ["agents", "registry"] });
  expect(await screen.findAllByText("edited-native-model · low")).toHaveLength(1);
  expect(screen.getByText("historical-verified-model")).toBeInTheDocument();
});

test("configuration load failures are visible instead of an empty registry", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Native agent file unavailable"));
  show();
  expect(await screen.findByText(/Unable to load agent configuration/)).toHaveTextContent("Native agent file unavailable");
});

function testRequests() {
  return vi.mocked(api).mock.calls.filter(([path, options]) =>
    options?.method === "POST" && path.endsWith("/test"),
  ).map(([path]) => path);
}

async function agentRow(id: string) {
  return (await screen.findByText(id, { selector: "strong" })).closest("tr")!;
}

test("testing one agent sends exactly one targeted request and leaves other agents enabled", async () => {
  const pending = deferred();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) =>
    path === "/agents/technical_analyst/test" ? pending.promise : defaultApi(path, options),
  );
  show();
  const analyst = within(await agentRow("technical_analyst"));
  const critic = within(await agentRow("critic"));
  const button = analyst.getByRole("button", { name: "Test" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(analyst.getByRole("button", { name: "Testing…" })).toBeDisabled();
  expect(critic.getByRole("button", { name: "Test" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Test all logical agents" })).toBeDisabled();
  await waitFor(() => expect(testRequests()).toEqual(["/agents/technical_analyst/test"]));
  await act(async () => pending.resolve({ execution: { status: "SUCCEEDED" }, result: { summary: "Analyst only" } }));
  await waitFor(() => expect(analyst.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(screen.getByText("technical_analyst · SUCCEEDED")).toBeInTheDocument();
  expect(testRequests()).toEqual(["/agents/technical_analyst/test"]);
});

test("different agent tests finish independently and preserve both results", async () => {
  const analystPending = deferred();
  const criticPending = deferred();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path === "/agents/technical_analyst/test") return analystPending.promise;
    if (path === "/agents/critic/test") return criticPending.promise;
    return defaultApi(path, options);
  });
  show();
  const analyst = within(await agentRow("technical_analyst"));
  const critic = within(await agentRow("critic"));
  fireEvent.click(analyst.getByRole("button", { name: "Test" }));
  fireEvent.click(critic.getByRole("button", { name: "Test" }));
  await waitFor(() => expect(testRequests()).toEqual(["/agents/technical_analyst/test", "/agents/critic/test"]));
  await act(async () => criticPending.resolve({ execution: { status: "SUCCEEDED" }, result: { summary: "Critic only" } }));
  await waitFor(() => expect(critic.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(analyst.getByRole("button", { name: "Testing…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Test all logical agents" })).toBeDisabled();
  await act(async () => analystPending.resolve({ execution: { status: "SUCCEEDED" }, result: { summary: "Analyst only" } }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Test all logical agents" })).toBeEnabled());
  expect(screen.getByText("critic · SUCCEEDED")).toBeInTheDocument();
  expect(screen.getByText("technical_analyst · SUCCEEDED")).toBeInTheDocument();
  expect(testRequests()).toHaveLength(2);
});

test("an individual test error stays on its agent and can be retried without automatic duplicates", async () => {
  const first = deferred();
  const second = deferred();
  let attempts = 0;
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path === "/agents/technical_analyst/test") return attempts++ ? second.promise : first.promise;
    return defaultApi(path, options);
  });
  show();
  const analyst = within(await agentRow("technical_analyst"));
  const critic = within(await agentRow("critic"));
  fireEvent.click(analyst.getByRole("button", { name: "Test" }));
  await waitFor(() => expect(testRequests()).toHaveLength(1));
  await act(async () => first.reject(new Error("Agent timed out")));
  expect(await analyst.findByRole("alert")).toHaveTextContent("Agent timed out");
  expect(critic.queryByRole("alert")).not.toBeInTheDocument();
  expect(testRequests()).toHaveLength(1);
  fireEvent.click(analyst.getByRole("button", { name: "Test" }));
  expect(analyst.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(testRequests()).toHaveLength(2));
  await act(async () => second.resolve({ execution: { status: "SUCCEEDED" } }));
  await waitFor(() => expect(analyst.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(critic.getByRole("button", { name: "Test" })).toBeEnabled();
});

test("bulk tests are explicit and cannot overlap individual tests or enqueue duplicates", async () => {
  const pending = deferred();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) =>
    path.endsWith("/test") ? pending.promise : defaultApi(path, options),
  );
  show();
  const analyst = within(await agentRow("technical_analyst"));
  const critic = within(await agentRow("critic"));
  const allButton = screen.getByRole("button", { name: "Test all logical agents" });
  fireEvent.click(allButton);
  fireEvent.click(allButton);
  fireEvent.click(analyst.getByRole("button", { name: "Testing…" }));
  expect(allButton).toBeDisabled();
  expect(critic.getByRole("button", { name: "Testing…" })).toBeDisabled();
  await waitFor(() => expect(testRequests()).toEqual(["/agents/technical_analyst/test", "/agents/critic/test"]));
  await act(async () => pending.resolve({ execution: { status: "SUCCEEDED" } }));
  await waitFor(() => expect(allButton).toBeEnabled());
  expect(testRequests()).toHaveLength(2);
});
