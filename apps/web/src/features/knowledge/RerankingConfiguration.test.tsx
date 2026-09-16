import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { api, type Resource } from "@/lib/api";
import { RerankingConfiguration, RerankingStatus } from "./RerankingConfiguration";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const configuration = { configured: false, connection_id: null, model: "rerank-v4.0-pro", candidate_limit: 50, verified_at: null };
const connections: Resource[] = [
  { id: "cohere", name: "My Cohere", provider: "COHERE", active: true, state: "ACTIVE" },
  { id: "disabled", name: "Disabled Cohere", provider: "COHERE", active: false, state: "ACTIVE" },
  { id: "openai", name: "Embedding provider", provider: "OPENAI", active: true, state: "ACTIVE" },
].map(item => ({ ...item, owner_id: "owner", kind: "connection", version: 1, created_at: "2026-09-16T10:00:00Z", updated_at: "2026-09-16T10:00:00Z" }));

function renderConfiguration() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><RerankingConfiguration connections={connections} /></QueryClientProvider>);
  return client;
}

it("saves the selected model and candidate pool, then can disable reranking", async () => {
  vi.mocked(api).mockImplementation(async (_path, options) => {
    if (options?.method === "PUT") return { ...configuration, ...JSON.parse(String(options.body)), configured: true, verified_at: "2026-09-16T10:00:00Z" };
    return configuration;
  });
  const client = renderConfiguration();
  expect(await screen.findByLabelText("Cohere connection")).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /Disabled Cohere|Embedding provider/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Cohere connection"), { target: { value: "cohere" } });
  fireEvent.change(screen.getByLabelText("Rerank model"), { target: { value: "rerank-v4.0-fast" } });
  fireEvent.change(screen.getByLabelText("Candidate pool"), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify and enable reranking" }));
  await screen.findByText(/Cohere verified/);
  expect(api).toHaveBeenCalledWith("/knowledge/reranking-configuration", {
    method: "PUT", body: JSON.stringify({ connection_id: "cohere", model: "rerank-v4.0-fast", candidate_limit: 30 }),
  });
  expect(screen.getByText(/Enabled · rerank-v4.0-fast/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disable reranking" }));
  await screen.findByText(/Reranking disabled. Knowledge retrieval/);
  expect(api).toHaveBeenCalledWith("/knowledge/reranking-configuration", { method: "DELETE" });
  expect(screen.queryByRole("button", { name: "Disable reranking" })).not.toBeInTheDocument();
  client.clear();
});

it("does not show an unsuccessful verification as enabled", async () => {
  vi.mocked(api).mockImplementation(async (_path, options) => {
    if (options?.method === "PUT") throw new Error("Cohere verification failed");
    return configuration;
  });
  const client = renderConfiguration();
  fireEvent.change(await screen.findByLabelText("Cohere connection"), { target: { value: "cohere" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify and enable reranking" }));
  await screen.findByText("Cohere verification failed");
  expect(screen.getByText(/Disabled · hybrid retrieval/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Verify and enable reranking" })).not.toBeDisabled());
  client.clear();
});

it("discloses hybrid fallback and successful reranking", () => {
  const view = render(<RerankingStatus result={{ status: "DEGRADED" }} />);
  expect(screen.getByRole("status")).toHaveTextContent("Cohere reranking unavailable; results use hybrid retrieval order.");
  view.rerender(<RerankingStatus result={{ status: "APPLIED", model: "rerank-v4.0-pro", candidate_count: 30 }} />);
  expect(screen.getByText("Reranked with rerank-v4.0-pro · 30 candidates")).toBeInTheDocument();
});
