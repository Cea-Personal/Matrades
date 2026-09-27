import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api, API_ROOT } from "@/lib/api";
import { Extras } from "./Extras";

const navigation = vi.hoisted(() => ({ folder: "market-research" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams({ folder: navigation.folder }) }));
vi.mock("@/lib/api", () => ({ api: vi.fn(), API_ROOT: "http://test-api/api/v1" }));

const folders = [
  { id: "market-research", label: "Market research", description: "Market cycles", count: 7 },
  { id: "strategy-research", label: "Strategy research", description: "Strategy cycles", count: 7 },
  { id: "trade-recommendations", label: "Trade recommendations", description: "Trade reasoning", count: 7 },
  { id: "generated-code", label: "Generated code", description: "Strategy source", count: 7 },
  { id: "mt5-bridge-ea", label: "MT5 bridge EA", description: "Read-only publisher", count: 1 },
];
const records = Object.fromEntries(folders.map(folder => [folder.id, Array.from({ length: folder.count }, (_, index) => ({
  id: `${folder.id}-${index}`, folder: folder.id, name: `${folder.label} record ${index}`,
  state: index === 6 ? "FAILED" : "COMPLETED", completed_at: `2026-09-${String(21 + index).padStart(2, "0")}T10:00:00Z`,
  summary: { instrument: index === 6 ? "XAUUSD" : "EURUSD", category: "CFD", reason: index === 6 ? "Provider unavailable" : null },
  details: { instrument: index === 6 ? "XAUUSD" : "EURUSD", action: "WAIT" },
  code: ["generated-code", "mt5-bridge-ea"].includes(folder.id) ? `// source-${index}` : undefined,
  download_path: folder.id === "mt5-bridge-ea" ? "/api/v1/extras/mt5-ea/download" : undefined,
  why: { evidence: ["Recorded evidence"] },
}))]));

beforeEach(() => { navigation.folder = "market-research"; vi.mocked(api).mockResolvedValue({ folders, items: records }); });
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); vi.unstubAllGlobals(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Extras /></QueryClientProvider>);
}

test.each(folders.filter(folder => folder.count > 3))("$label shows its three newest records and expands in batches", async folder => {
  navigation.folder = folder.id;
  show();
  const archive = await screen.findByRole("region", { name: `${folder.label} archive` });
  const cards = within(archive);
  await screen.findByText(`${folder.label} record 6`);
  expect(cards.getAllByRole("article")).toHaveLength(3);
  expect(cards.getAllByRole("heading", { level: 3 }).map(item => item.textContent)).toEqual([6, 5, 4].map(index => `${folder.label} record ${index}`));
  fireEvent.click(cards.getByRole("button", { name: "Load more archive records" }));
  expect(cards.getAllByRole("article")).toHaveLength(6);
  fireEvent.click(cards.getByRole("button", { name: "Load more archive records" }));
  expect(cards.getAllByRole("article")).toHaveLength(7);
  fireEvent.click(cards.getByRole("button", { name: "Show fewer archive records" }));
  expect(cards.getAllByRole("article")).toHaveLength(3);
});

test("filters the full folder, keeps failure reasons visible and distinguishes no matches", async () => {
  show();
  await screen.findByText("Market research record 6");
  expect(screen.getByText("Provider unavailable", { selector: "p" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search this folder" }), { target: { value: "EURUSD" } });
  expect(screen.queryByRole("heading", { name: "Market research record 6" })).not.toBeInTheDocument();
  expect(screen.getByText("Showing 3 of 6 archive records")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "XAUUSD" } });
  expect(screen.getByRole("heading", { name: "Market research record 6" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Record status" }), { target: { value: "COMPLETED" } });
  expect(screen.getByText("No records match these filters.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show all records" }));
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(screen.getByText("Showing 3 of 7 archive records")).toBeInTheDocument();
});

test("URL changes override previous selections and reset filters and record limits", async () => {
  const view = show();
  await screen.findByText("Market research record 6");
  fireEvent.click(screen.getByRole("button", { name: "Load more archive records" }));
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "EURUSD" } });
  navigation.folder = "strategy-research";
  view.rerender(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Extras /></QueryClientProvider>);
  await screen.findByText("Strategy research record 6");
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(screen.getByText("Showing 3 of 7 archive records")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Market research record 6" })).not.toBeInTheDocument();
  const nav = within(screen.getByRole("navigation", { name: "Extras folders" }));
  expect(nav.getByRole("link", { name: /Strategy research/ })).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", { name: /Generated code/ })).toHaveAttribute("href", "/extras?folder=generated-code");
});

test("EA source stays collapsed and its download URL does not duplicate the API prefix", async () => {
  navigation.folder = "mt5-bridge-ea";
  const { container } = show();
  await screen.findByText("MT5 bridge EA record 0");
  expect(container.querySelector('details[open]')).toBeNull();
  expect(screen.getByRole("link", { name: "Download .mq5" })).toHaveAttribute("href", `${API_ROOT}/extras/mt5-ea/download`);
  expect(screen.getByRole("button", { name: "Copy .mq5 code" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Load more archive records" })).not.toBeInTheDocument();
});

test("copy feedback belongs only to the selected source artifact", async () => {
  navigation.folder = "generated-code";
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  show();
  await screen.findByText("Generated code record 6");
  fireEvent.click(screen.getAllByRole("button", { name: "Copy code" })[0]);
  expect(await screen.findAllByRole("button", { name: "Copied" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "Copy code" })).toHaveLength(2);
  expect(writeText).toHaveBeenCalledWith("// source-6");
});

test("empty folders and failed retrieval have distinct messages", async () => {
  vi.mocked(api).mockResolvedValue({ folders, items: {} });
  show();
  expect(await screen.findByText("No records in this folder yet. New evidence will appear here automatically.")).toBeInTheDocument();
  cleanup();
  vi.mocked(api).mockRejectedValue(new Error("Offline"));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load Extras: Offline");
});
