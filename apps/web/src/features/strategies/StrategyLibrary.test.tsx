import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { StrategyLibrary } from "./StrategyLibrary";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><StrategyLibrary /></QueryClientProvider>);
}

test("displays OOS regime evidence and explicitly simulated health windows", async () => {
  vi.mocked(api).mockResolvedValue([{
    strategy_version_id: "v1", name: "Gold breakout", instrument: "XAUUSD", family: "BREAKOUT", state: "SUSPENDED", timeframe: "1h", account_id: "account",
    regime_performance: { "TRENDING:BULLISH:HIGH_VOLATILITY": { trade_count: 12, average_r: 0.8, win_rate: 0.6, profit_factor_r: 2 } },
    recent: { trade_count: 30, average_r: -0.2 }, recent_basis: "FORWARD_SHADOW",
    health: { status: "DEGRADED", reason: "Lost edge", windows: { "30": { trade_count: 30, average_r: -0.2, complete: true }, "60": { trade_count: 30, average_r: -0.2, complete: false } } },
    selection: { selected_version_id: null }, robustness: { research_selection_cut_at: "2026-09-22T12:00:00Z", holdout_start_at: null },
    execution_validation: { engine: "NautilusTrader", status: "COMPLETED", passed: false, trade_count: 5, data_basis: "ASSUMED_OHLC_ADVERSE_FIRST_WITH_CONFIGURED_SPREAD" },
  }]);
  show();
  expect(await screen.findByText("XAUUSD · BREAKOUT · SUSPENDED")).toBeInTheDocument();
  expect(screen.getByText("TRENDING:BULLISH:HIGH_VOLATILITY")).toBeInTheDocument();
  expect(screen.getByText(/30\/60\/100-trade windows/)).toHaveTextContent("not broker executions");
  expect(screen.getByText(/Last 30:/)).toHaveTextContent("complete");
  expect(screen.getByText(/Last 60:/)).toHaveTextContent("warming up");
  expect(screen.getByText(/Waiting for sufficient new candles/)).toBeInTheDocument();
  expect(screen.getByText("No eligible strategy for the current regime.")).toBeInTheDocument();
  expect(screen.getByText(/NautilusTrader · COMPLETED/)).toHaveTextContent("Not eligible for paper promotion");
  expect(screen.getByText(/5 simulated trades/)).toHaveTextContent("ASSUMED OHLC");
});

test("shows an unavailable evidence error instead of a false empty success", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Offline"));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
});
