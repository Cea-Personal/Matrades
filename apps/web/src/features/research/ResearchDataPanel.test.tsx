import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { ResearchDataPanel } from "./ResearchDataPanel";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show(accountId = "account") {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ResearchDataPanel accountId={accountId} /></QueryClientProvider>);
}

test("shows an insufficient-data experiment without assuming a completed grid", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/research-data/experiments?account_id=account") return [{ id: "experiment", instrument: "EUR/USD", status: "INSUFFICIENT_DISCOVERY_HISTORY", engine: "vectorbt", combination_count: 0, outer_holdout_used: false }];
    if (path === "/research-data/experiments/experiment/results") return { status: "INSUFFICIENT_DISCOVERY_HISTORY" };
    return [];
  });
  show();
  fireEvent.change(await screen.findByLabelText("Quantitative experiment"), { target: { value: "experiment" } });
  expect(await screen.findByText(/Unit-size fast-research PnL/)).toBeInTheDocument();
  expect(screen.getByText(/Outer holdout used for optimization/)).toHaveTextContent("No");
  expect(screen.queryByText("Selected for held-out screening")).not.toBeInTheDocument();
});

test("does not fetch another account's experiment after switching accounts", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/research-data/experiments?account_id=account") return [{ id: "experiment", instrument: "EUR/USD", status: "COMPLETED", engine: "vectorbt", combination_count: 1, outer_holdout_used: false }];
    if (path === "/research-data/experiments/experiment/results") return { experiments: [] };
    return [];
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><ResearchDataPanel accountId="account" /></QueryClientProvider>);
  fireEvent.change(await screen.findByLabelText("Quantitative experiment"), { target: { value: "experiment" } });
  await screen.findByText(/Unit-size fast-research PnL/);
  const previous = vi.mocked(api).mock.calls.filter(([path]) => path === "/research-data/experiments/experiment/results").length;
  view.rerender(<QueryClientProvider client={client}><ResearchDataPanel accountId="other" /></QueryClientProvider>);
  await screen.findByText(/Selected-pair research automatically records/);
  expect(screen.queryByText(/Unit-size fast-research PnL/)).not.toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/research-data/experiments/experiment/results")).toHaveLength(previous);
});

test("reports unavailable data explicitly", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Offline"));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Research data could not be loaded");
});

test("requires account selection before querying datasets", async () => {
  vi.mocked(api).mockResolvedValue([]);
  show("");
  expect(screen.getByText("Select an account to inspect its research data.")).toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.every(([path]) => !path.startsWith("/research-data/"))).toBe(true);
});
