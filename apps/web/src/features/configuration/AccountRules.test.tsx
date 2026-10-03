import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { AccountRules } from "./AccountRules";

vi.mock("@/lib/api", () => ({ api: vi.fn(), withStepUp: vi.fn() }));
vi.mock("./StrategyAutomationPolicy", () => ({ StrategyAutomationPolicy: () => null }));

afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

test("account creation records both starting and opening current balance", async () => {
  let saved: Record<string, unknown> | null = null;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === "/configuration/accounts" && options?.method === "POST") {
      saved = JSON.parse(String(options.body)) as Record<string, unknown>;
      return { id: "account-1", state: "ACTIVE", version: 1, ...saved };
    }
    if (path === "/configuration/accounts") {
      return saved ? [{ id: "account-1", state: "ACTIVE", version: 1, ...saved }] : [];
    }
    if (path === "/configuration/effective-limits") return { contributors: [], effective: {} };
    return [];
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AccountRules /></QueryClientProvider>);
  fireEvent.click(screen.getByText("Add an account or risk rule"));
  const form = screen.getByText("Add trading account").closest("form")!;
  fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Primary" } });
  fireEvent.change(within(form).getByLabelText("Starting balance"), { target: { value: "10000" } });
  fireEvent.change(within(form).getByLabelText("Current balance at setup"), { target: { value: "8500" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save account" }));
  await waitFor(() => expect(saved).toMatchObject({
    name: "Primary", starting_balance: "10000", current_balance: "8500",
  }));
  expect(await screen.findByText("Balance at setup")).toBeInTheDocument();
  expect(screen.getByText("8500", { selector: "td" })).toBeInTheDocument();
});
