import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { OverviewDashboard } from "./OverviewDashboard";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show(points: Array<{ id: string; observed_at: string; equity: string; balance: string }>) {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/configuration/accounts") return [{
      id: "account-1", name: "Primary", state: "ACTIVE", currency: "USD",
      starting_balance: "10000", current_balance: "8500", created_at: "2026-09-01T00:00:00Z",
    }];
    if (path.startsWith("/automation/equity-history")) return {
      account_id: "account-1", currency: "USD", points,
    };
    if (path.startsWith("/configuration/effective-limits")) return { effective: {} };
    if (path === "/automation/operations") return {
      active_trades: [], trade_plans: [], execution_commands: [], execution_mode: "AUTONOMOUS",
    };
    if (path === "/operations/health") return { state: "HEALTHY", components: [] };
    return [];
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OverviewDashboard /></QueryClientProvider>);
}

test("shows the entered balance as setup information without presenting it as broker equity", async () => {
  show([]);
  expect(await screen.findByText("$8,500")).toBeInTheDocument();
  expect(screen.getByText(/Balance entered at setup/)).toBeInTheDocument();
  expect(screen.getByText("-$1,500")).toBeInTheDocument();
  expect(screen.getByText(/Trade sizing requires a fresh broker snapshot/)).toBeInTheDocument();
});

test("broker balance supersedes the entered balance and equity change uses the starting baseline", async () => {
  show([{ id: "snapshot-1", observed_at: "2026-10-03T13:00:00Z", equity: "8800", balance: "9000" }]);
  expect(await screen.findByText("$8,800")).toBeInTheDocument();
  expect(screen.getByText(/Broker balance/)).toBeInTheDocument();
  expect(screen.getByText("$9,000")).toBeInTheDocument();
  expect(screen.getByText("-$1,000")).toBeInTheDocument();
  expect(screen.getByText("-12.0%")).toBeInTheDocument();
});
