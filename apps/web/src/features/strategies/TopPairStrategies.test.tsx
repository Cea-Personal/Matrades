import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TradeSetupSummary } from "./TopPairStrategies";

afterEach(() => { cleanup(); vi.useRealTimers(); });

it("shows strategy levels and removes them when price evidence expires", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-15T12:00:00Z"));
  render(<TradeSetupSummary setup={{
    status: "SIGNAL", direction: "LONG", entry: "100", stop_loss: "98",
    take_profits: [{ price: "104", reward_risk: "2", fraction: "1" }],
    expires_at: "2026-09-15T12:00:01Z", risk_per_trade_percent: "0.5",
  }} />);
  expect(screen.getByText("100")).toBeInTheDocument();
  expect(screen.getByText("98")).toBeInTheDocument();
  expect(screen.getByText(/104 · 2.00R/)).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(1000); });
  expect(screen.getByText(/Trade setup · STALE/)).toBeInTheDocument();
  expect(screen.queryByText("100")).not.toBeInTheDocument();
});
