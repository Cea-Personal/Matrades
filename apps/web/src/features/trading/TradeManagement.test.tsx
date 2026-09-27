import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { TradeManagement } from "./TradeManagement";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

test("the actual trading screen shows plan and broker evidence without trading actions", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/automation/operations") return {
      execution_mode: "AUTONOMOUS",
      trade_plans: [{ id: "plan", instrument: "EURUSD", state: "EXECUTED", risk: { decision: "ALLOW" }, updated_at: "2026-09-27T10:00:00Z" }],
      active_trades: [{ id: "trade", state: "OPEN", trade_plan_id: "plan", broker_position: { instrument: "EURUSD", direction: "BUY", stop_loss: "1.10", pnl: "25" } }],
      execution_commands: [{ id: "command", action: "PLACE_ORDER", state: "APPLIED", outcome_certainty: "CONFIRMED", broker_order_id: "broker-order", idempotency_key: "persisted-key", updated_at: "2026-09-27T10:00:00Z" }],
    };
    return { freshness: "FRESH", mapping_status: "MAPPED", candles: [], overlays: [] };
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><TradeManagement /></QueryClientProvider>);
  const row = (await screen.findByText("EURUSD", { selector: "td strong" })).closest("tr")!;
  expect(within(row).getByText("Risk ALLOW")).toBeInTheDocument();
  expect(within(row).getByText("Stop 1.10")).toBeInTheDocument();
  expect(screen.getByText("CONFIRMED")).toBeInTheDocument();
  expect(screen.getByText("persisted-key")).toBeInTheDocument();
  expect(screen.getByText(/not an approval queue/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /approve|reject|place order|take manually/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("EURUSD · position chart"));
  await screen.findByText("FRESH · MAPPED");
  fireEvent.change(screen.getByRole("combobox", { name: "Timeframe" }), { target: { value: "4h" } });
  await waitFor(() => expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("?timeframe=4h"))).toBe(true));
  expect(vi.mocked(api).mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
});
