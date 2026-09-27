import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { StrategyBuilder } from "./StrategyBuilder";

vi.mock("@/lib/api", () => ({ api: vi.fn(), API_ROOT: "http://test-api/api/v1" }));

const apiMock = vi.mocked(api);

function showBuilder(context: unknown) {
  apiMock.mockImplementation(async path => path === "/strategies/research-context" ? context : []);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StrategyBuilder /></QueryClientProvider>);
}

beforeEach(() => apiMock.mockReset());
afterEach(() => cleanup());

test("shows every pair in the current market cycle", async () => {
  const selections = ["AUD/USD", "XAUEUR", "BTC-USD", "AAPL"].map((instrument, index) => ({
    ready: true,
    reason: null,
    market_selection_id: `selection-${index}`,
    instrument,
    category: "CFD",
    market_observed_at: "2026-09-24T16:00:00Z",
    historical_provider: "MT5_BRIDGE",
  }));
  showBuilder({ ready: true, reason: null, market_research_run_id: "current-cycle", market_research_state: "COMPLETED", selections });
  await waitFor(() => expect(screen.getByText("Cycle current-cycle · COMPLETED.", { exact: false })).toBeInTheDocument());
  for (const instrument of ["AUD/USD", "XAUEUR", "BTC-USD", "AAPL"]) {
    expect(screen.getAllByText(`${instrument} · CFD`)).toHaveLength(2);
  }
  fireEvent.click(screen.getByText("Manual strategy generation"));
  expect(screen.getByRole("combobox", { name: "Latest-cycle pair" })).toHaveValue("selection-0");
});

test("shows a version mismatch instead of crashing when the API returns the old shape", async () => {
  showBuilder({ ready: true, reason: null, instrument: "EUR/USD" });
  expect(await screen.findByText(/running an older version/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Manual strategy generation"));
  expect(screen.getByRole("button", { name: "Generate strategy" })).toBeDisabled();
});

function showApprovalFlow(failDecision = false) {
  let state = "AWAITING_STRATEGY_APPROVAL";
  let createdVersion = false;
  const specification = { name: "AUD momentum", family: "MOMENTUM", horizon: "INTRADAY", instruments: ["AUD/USD"], risk_per_trade: 0.5 };
  apiMock.mockImplementation(async (path, options) => {
    if (path === "/strategies/research-context") return { ready: true, selections: [], market_research_run_id: "cycle", market_research_state: "COMPLETED" };
    if (path === "/strategies") return [{ id: "draft", state, origin: "AI_GENERATED", proposed_specification: specification, research_basis: { market_research_run_id: "cycle", instrument: "AUD/USD" } }];
    if (path === "/strategies/drafts/draft/proposal-decision") {
      if (failDecision) throw new Error("Decision denied");
      const action = JSON.parse(String(options?.body)).action;
      state = action === "APPROVE" ? "DRAFT" : "REJECTED";
      return { id: "draft", state };
    }
    if (path === "/strategies/submit/draft") {
      state = "SPECIFIED";
      createdVersion = true;
      return { id: "version", state: "IMPLEMENTED", specification };
    }
    if (path === "/strategies/versions") return createdVersion ? [{ id: "version", state: "IMPLEMENTED", specification, backtest_basis: { ready: true, instrument: "AUD/USD", historical_connection_id: "provider", historical_provider: "TWELVE_DATA" } }] : [];
    if (path === "/configuration/connections") return [{ id: "wrong-provider", state: "ACTIVE", name: "Crypto prices", provider: "COINBASE" }, { id: "provider", state: "ACTIVE", name: "Historical prices", provider: "TWELVE_DATA" }];
    return [];
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StrategyBuilder /></QueryClientProvider>);
}

test("acceptance enables version creation and selects that version for backtesting", async () => {
  showApprovalFlow();
  fireEvent.click(await screen.findByRole("button", { name: "Accept proposal" }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/strategies/drafts/draft/proposal-decision", { method: "POST", body: JSON.stringify({ action: "APPROVE" }) }));
  fireEvent.click(await screen.findByRole("button", { name: "Create strategy version" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Strategy version" })).toHaveValue("version"));
  expect(screen.getByRole("textbox", { name: "Instrument" })).toHaveValue("AUD/USD");
  expect(screen.getByRole("button", { name: "Run backtest" })).toBeEnabled();
  expect(screen.getByRole("combobox", { name: "Historical data source" })).toHaveValue("provider");
  expect(screen.getByRole("combobox", { name: "Historical data source" })).toBeDisabled();
  expect(screen.queryByRole("option", { name: "Crypto prices · COINBASE" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start paper session" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Create Trade Plan" })).toBeDisabled();
});

test("rejecting a proposal does not create a version or start a backtest", async () => {
  showApprovalFlow();
  fireEvent.click(await screen.findByRole("button", { name: "Reject proposal" }));
  await waitFor(() => expect(screen.getByText("REJECTED", { exact: true })).toBeInTheDocument());
  expect(apiMock).toHaveBeenCalledWith("/strategies/drafts/draft/proposal-decision", { method: "POST", body: JSON.stringify({ action: "REJECT" }) });
  expect(screen.queryByRole("button", { name: "Create strategy version" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Backtest & paper" }));
  expect(screen.getByRole("button", { name: "Run backtest" })).toBeDisabled();
});

test("failed approval keeps proposal actions available and displays the error", async () => {
  showApprovalFlow(true);
  fireEvent.click(await screen.findByRole("button", { name: "Accept proposal" }));
  expect(await screen.findByText("Decision denied")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Accept proposal" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Create strategy version" })).not.toBeInTheDocument();
});

test.each([
  ["IMPLEMENTED", false, false],
  ["VALIDATING", true, false],
  ["APPROVED", false, false],
])("paper and Trade Plan actions respect validation state %s", async (state, startEnabled, planEnabled) => {
  apiMock.mockImplementation(async path => {
    if (path === "/strategies/versions") return [{
      id: "version", state, specification: { name: "Validated strategy" },
      validation_evidence: { backtest: state !== "IMPLEMENTED", out_of_sample: true, walk_forward: true, stress: true, policy: true, paper: state === "APPROVED" },
    }];
    if (path === "/strategies/research-context") return { ready: false, selections: [] };
    return [];
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><StrategyBuilder /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("tab", { name: "Backtest & paper" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Strategy version" })).toHaveValue("version"));
  const start = screen.getByRole("button", { name: "Start paper session" });
  const plan = screen.getByRole("button", { name: "Create Trade Plan" });
  if (startEnabled) expect(start).toBeEnabled(); else expect(start).toBeDisabled();
  if (planEnabled) expect(plan).toBeEnabled(); else expect(plan).toBeDisabled();
  expect(screen.getByRole("button", { name: "Finish and review paper results" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Record paper evidence" })).not.toBeInTheDocument();
});

test.each([
  ["APPROVED", true, "SIGNAL", true, false],
  ["APPROVED", false, "SIGNAL", false, false],
  ["ACTIVE", true, "SIGNAL", false, true],
  ["ACTIVE", true, "WAIT", false, false],
])("activation and live signals are separate for %s / %s / %s", async (state, forward, status, activateEnabled, planEnabled) => {
  const version = { id: "version", state, specification: { name: "Forward-tested" }, validation_evidence: { paper: true, paper_forward: forward } };
  apiMock.mockImplementation(async path => {
    if (path === "/strategies/versions") return [version];
    if (path === "/strategies/monitoring") return [{ ...version, latest_signal: { status, mode: "LIVE", expires_at: "2099-01-01T00:00:00Z" } }];
    if (path === "/strategies/research-context") return { ready: false, selections: [] };
    return [];
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><StrategyBuilder /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("tab", { name: "Backtest & paper" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Strategy version" })).toHaveValue("version"));
  const activate = screen.getByRole("button", { name: "Activate strategy" });
  const plan = screen.getByRole("button", { name: "Create Trade Plan" });
  if (activateEnabled) expect(activate).toBeEnabled(); else expect(activate).toBeDisabled();
  if (planEnabled) expect(plan).toBeEnabled(); else expect(plan).toBeDisabled();
});
