import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
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
