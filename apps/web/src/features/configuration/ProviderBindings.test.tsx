import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { deferred } from "@/test/deferred";
import { ProviderBindings } from "./ProviderBindings";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const accounts = [
  { id: "primary", name: "Primary", state: "ACTIVE", version: 1 },
  { id: "secondary", name: "Secondary", state: "ACTIVE", version: 1 },
];
const matrix = { version: 2, lanes: [{ asset_class: "FOREX", instrument_type: "CFD", enabled: true }] };
const plan = {
  id: "recommendation", account_id: "primary", state: "RECOMMENDED", matrix_version: 2,
  mode: "AI_ASSISTED", message: "Recommendations checked.", stale: false,
  suggestions: [
    { candidate_id: "discovery", lane: matrix.lanes[0], capability: "DISCOVERY", authority_purpose: "DISCOVERY", connection_name: "Forex source", status: "READY", reason: "Supported forex discovery.", notes: [] },
    { candidate_id: "history", lane: matrix.lanes[0], capability: "CANDLES", authority_purpose: "HISTORY", connection_name: "History source", status: "NEEDS_TEST", reason: "Independent history.", notes: ["Test before verification."] },
    { candidate_id: "covered", lane: null, capability: "ECONOMIC_CALENDAR", authority_purpose: "REFERENCE", connection_name: "Calendar", status: "ALREADY_BOUND", reason: "Existing calendar coverage.", notes: [] },
  ],
  gaps: [{ lane: "METALS:CFD", reason: "Configure an MT5 Bridge." }],
};

beforeEach(() => {
  vi.mocked(api).mockImplementation(async (path, init) => {
    if (path === "/configuration/accounts") return accounts;
    if (path === "/configuration/connections") return [];
    if (path.endsWith("research-matrix")) return matrix;
    if (path.endsWith("provider-bindings")) return [];
    if (path.endsWith("provider-binding-suggestions")) return init?.method === "POST" ? plan : null;
    if (path.endsWith("provider-binding-suggestions/apply")) return { verified_count: 1, unverified_count: 0 };
    throw new Error(`Unexpected request: ${path}`);
  });
});
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProviderBindings /></QueryClientProvider>);
}

function writes() {
  return vi.mocked(api).mock.calls.filter(([, init]) => init?.method === "POST");
}

test("AI suggestions are reviewed before applying only selected bindings to the selected account", async () => {
  show();
  await screen.findByRole("option", { name: "Primary" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Suggest bindings with AI" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Suggest bindings with AI" }));
  expect(await screen.findByText("Supported forex discovery.")).toBeInTheDocument();
  expect(screen.getByText("Already verified")).toBeInTheDocument();
  expect(screen.getByText("METALS · CFD: Configure an MT5 Bridge.")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Apply FOREX · CFD DISCOVERY Forex source" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Apply FOREX · CFD CANDLES History source" })).not.toBeChecked();
  expect(writes()).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Apply 1 selected bindings" }));
  await screen.findByRole("status");
  const applyRequest = writes().find(([path]) => path.endsWith("/apply"))!;
  expect(applyRequest[0]).toBe("/accounts/primary/provider-binding-suggestions/apply");
  expect(JSON.parse(String(applyRequest[1]?.body))).toEqual({ recommendation_id: "recommendation", candidate_ids: ["discovery"] });
  expect(writes().some(([path]) => path.includes("/configuration/connections/"))).toBe(false);
});

test("account switching cannot display or apply a previous account's delayed recommendations", async () => {
  const pending = deferred<typeof plan>();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, init) => path === "/accounts/primary/provider-binding-suggestions" && init?.method === "POST"
    ? pending.promise : defaultApi(path, init));
  show();
  await screen.findByRole("option", { name: "Primary" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Suggest bindings with AI" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Suggest bindings with AI" }));
  await waitFor(() => expect(writes()).toHaveLength(1));
  fireEvent.change(screen.getByRole("combobox", { name: "Trading account" }), { target: { value: "secondary" } });
  await act(async () => pending.resolve(plan));
  expect(screen.queryByText("Supported forex discovery.")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Apply 1 selected bindings" })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(1);
});

test("stale saved suggestions cannot be applied and rule based fallback is clearly labeled", async () => {
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, init) => path.endsWith("provider-binding-suggestions")
    ? Promise.resolve({ ...plan, stale: true, mode: "RULE_BASED", message: "AI unavailable; compatible sources shown." })
    : defaultApi(path, init));
  show();
  await screen.findByText("Your configuration changed. Generate new suggestions before applying them.");
  expect(screen.getByText(/Rule based · Matrix v2/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply 1 selected bindings" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "Apply FOREX · CFD DISCOVERY Forex source" })).toBeDisabled();
  expect(writes()).toHaveLength(0);
});
