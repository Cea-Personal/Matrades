import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { deferred } from "@/test/deferred";
import { Connections } from "./Connections";

vi.mock("@/lib/api", () => ({ api: vi.fn(), withStepUp: vi.fn() }));

const sources = ["Coinbase primary", "Coinbase secondary"].map((name, index) => ({
  id: `source-${index}`, name, provider: "COINBASE", health: "UNTESTED", state: "ACTIVE",
  active: true, capabilities: [], last_checked: null, updated_at: "2026-09-27T10:00:00Z",
}));

beforeEach(() => {
  vi.mocked(api).mockImplementation(async path =>
    path === "/configuration/connections" ? sources : [],
  );
});
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Connections /></QueryClientProvider>);
}

function testRequests() {
  return vi.mocked(api).mock.calls.filter(([path, options]) =>
    options?.method === "POST" && path.endsWith("/test"),
  ).map(([path]) => path);
}

async function sourceRow(name: string) {
  return (await screen.findByText(name, { selector: "td" })).closest("tr")!;
}

test("the live connection form exposes MT5 configuration and masks its authoritative secret", async () => {
  show();
  await sourceRow(sources[0].name);
  fireEvent.click(screen.getByText("Add a connection or credential"));
  fireEvent.change(screen.getByRole("combobox", { name: "Data source" }), { target: { value: "MT5_BRIDGE" } });
  expect(screen.getByRole("textbox", { name: "Bridge URL" })).toHaveValue("http://host.docker.internal:8765");
  expect(screen.getByRole("textbox", { name: "Account reference" })).toBeRequired();
  expect(screen.getByRole("combobox", { name: "Encrypted credential" })).toBeRequired();
  fireEvent.change(screen.getByRole("combobox", { name: /^Provider$/ }), { target: { value: "MT5_BRIDGE" } });
  expect(screen.getByLabelText("Authoritative bridge secret")).toHaveAttribute("type", "password");
  expect(screen.getByRole("button", { name: "Generate secure secret" })).toBeEnabled();
  expect(screen.getByText("InpBridgeSecret")).toBeInTheDocument();
  expect(testRequests()).toHaveLength(0);
});

test("one source test sends only its own request and leaves other sources available", async () => {
  const pending = deferred();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) =>
    path === "/configuration/connections/source-0/test" ? pending.promise : defaultApi(path, options),
  );
  show();
  const primary = within(await sourceRow(sources[0].name));
  const secondary = within(await sourceRow(sources[1].name));
  const button = primary.getByRole("button", { name: "Test" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(primary.getByRole("button", { name: "Testing…" })).toBeDisabled();
  expect(secondary.getByRole("button", { name: "Test" })).toBeEnabled();
  await waitFor(() => expect(testRequests()).toEqual(["/configuration/connections/source-0/test"]));
  await act(async () => pending.resolve({ ...sources[0], health: "HEALTHY" }));
  expect(await primary.findByRole("status")).toHaveTextContent("Coinbase primary is HEALTHY");
  await waitFor(() => expect(primary.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(secondary.queryByRole("status")).not.toBeInTheDocument();
  expect(testRequests()).toHaveLength(1);
});

test("parallel source tests finish independently without overwriting each other's results", async () => {
  const first = deferred();
  const second = deferred();
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path === "/configuration/connections/source-0/test") return first.promise;
    if (path === "/configuration/connections/source-1/test") return second.promise;
    return defaultApi(path, options);
  });
  show();
  const primary = within(await sourceRow(sources[0].name));
  const secondary = within(await sourceRow(sources[1].name));
  fireEvent.click(primary.getByRole("button", { name: "Test" }));
  fireEvent.click(secondary.getByRole("button", { name: "Test" }));
  await waitFor(() => expect(testRequests()).toHaveLength(2));
  await act(async () => second.resolve({ ...sources[1], health: "STALE", last_error: "Waiting for data" }));
  await waitFor(() => expect(secondary.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(primary.getByRole("button", { name: "Testing…" })).toBeDisabled();
  await act(async () => first.resolve({ ...sources[0], health: "HEALTHY" }));
  expect(await primary.findByRole("status")).toHaveTextContent("Coinbase primary is HEALTHY");
  expect(secondary.getByRole("status")).toHaveTextContent("Coinbase secondary is STALE · Waiting for data");
  expect(testRequests()).toEqual([
    "/configuration/connections/source-0/test", "/configuration/connections/source-1/test",
  ]);
});

test("errors stay with their source and retrying does not trigger other source checks", async () => {
  const first = deferred();
  const second = deferred();
  let attempts = 0;
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path === "/configuration/connections/source-0/test") return attempts++ ? second.promise : first.promise;
    return defaultApi(path, options);
  });
  show();
  const primary = within(await sourceRow(sources[0].name));
  const secondary = within(await sourceRow(sources[1].name));
  fireEvent.click(primary.getByRole("button", { name: "Test" }));
  await waitFor(() => expect(testRequests()).toHaveLength(1));
  await act(async () => first.reject(new Error("Provider timed out")));
  expect(await primary.findByRole("alert")).toHaveTextContent("Provider timed out");
  expect(secondary.queryByRole("alert")).not.toBeInTheDocument();
  expect(testRequests()).toHaveLength(1);
  fireEvent.click(primary.getByRole("button", { name: "Test" }));
  expect(primary.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(testRequests()).toHaveLength(2));
  await act(async () => second.resolve({ ...sources[0], health: "HEALTHY" }));
  await waitFor(() => expect(primary.getByRole("button", { name: "Test" })).toBeEnabled());
  expect(testRequests()).toEqual(Array(2).fill("/configuration/connections/source-0/test"));
});

test("cached Twelve Data results retain the quota explanation for that source", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/configuration/connections") return [
      { ...sources[0], provider: "TWELVE_DATA", name: "Forex primary" }, sources[1],
    ];
    if (path === "/configuration/connections/source-0/test") return {
      ...sources[0], name: "Forex primary", health: "HEALTHY", health_cached: true,
    };
    return [];
  });
  show();
  const forex = within(await sourceRow("Forex primary"));
  fireEvent.click(forex.getByRole("button", { name: "Test" }));
  expect(await forex.findByRole("status")).toHaveTextContent("cached; Twelve Data checks run at most once per hour");
  expect(testRequests()).toEqual(["/configuration/connections/source-0/test"]);
});

test("a provider reporting OFFLINE is shown as a failure rather than a successful check", async () => {
  const defaultApi = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) =>
    path === "/configuration/connections/source-0/test"
      ? Promise.resolve({ ...sources[0], health: "OFFLINE", last_error: "Connection refused" })
      : defaultApi(path, options),
  );
  show();
  const primary = within(await sourceRow(sources[0].name));
  fireEvent.click(primary.getByRole("button", { name: "Test" }));
  expect(await primary.findByRole("alert")).toHaveTextContent("Coinbase primary is OFFLINE · Connection refused");
});

test("hiding and redisplaying a source retains its busy state and prevents duplicate checks", async () => {
  const pending = deferred();
  const manySources = Array.from({ length: 8 }, (_, index) => ({
    ...sources[0], id: `source-${index}`, name: `Source ${index}`,
  }));
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/configuration/connections") return manySources;
    if (path === "/configuration/connections/source-7/test") return pending.promise;
    return [];
  });
  show();
  await sourceRow("Source 0");
  fireEvent.click(screen.getByRole("button", { name: "Load more data sources" }));
  const button = within(await sourceRow("Source 7")).getByRole("button", { name: "Test" });
  fireEvent.click(button);
  await waitFor(() => expect(testRequests()).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: "Show fewer data sources" }));
  expect(screen.queryByText("Source 7", { selector: "td" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load more data sources" }));
  const row = within(await sourceRow("Source 7"));
  expect(row.getByRole("button", { name: "Testing…" })).toBeDisabled();
  fireEvent.click(row.getByRole("button", { name: "Testing…" }));
  expect(testRequests()).toHaveLength(1);
  await act(async () => pending.resolve({ ...manySources[7], health: "HEALTHY" }));
  await waitFor(() => expect(row.getByRole("button", { name: "Test" })).toBeEnabled());
});
