import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketsWorkspace } from "./MarketsWorkspace";

function json(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("MarketsWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("runs research and requires deliberate approval before activating a candidate", async () => {
    let active: object[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.includes("/markets/instruments")) {
        return json({ items: [{ id: "instrument-1", symbol: "EURUSD", display_name: "Euro / US Dollar", category: "FOREX", status: "INACTIVE", data_status: "VERIFIED" }] });
      }
      if (path.endsWith("/markets/active") && (!init?.method || init.method === "GET")) {
        return json({ items: active, maximum: 3 });
      }
      if (path.endsWith("/markets/research") && init?.method === "POST") {
        return json({ run_id: "run-1", state: "COMPLETED" }, 202);
      }
      if (path.endsWith("/markets/research/run-1")) {
        return json({
          id: "run-1",
          category: "FOREX",
          state: "COMPLETED",
          methodology_version: "market-suitability-v1",
          input_manifest_hash: "manifest",
          completed_at: "2026-08-13T20:00:00Z",
          ranking_is_not_activation: true,
          candidates: [{
            id: "candidate-1",
            symbol: "EURUSD",
            display_name: "Euro / US Dollar",
            eligible: true,
            score: "0.81",
            rank: 1,
            confidence: "0.90",
            exclusions: [],
            components: { volatility: "0.8", liquidity: "0.9", cost_quality: "0.7" }
          }]
        });
      }
      if (path.endsWith("/markets/active/FOREX") && init?.method === "PUT") {
        active = [{ id: "assignment-1", category: "FOREX", symbol: "EURUSD", state: "ACTIVE", version: 1, etag: '"active-FOREX-1"' }];
        return json(active[0] as object);
      }
      return json({ detail: `Unhandled request ${path}` }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MarketsWorkspace />);
    const runButton = await screen.findByRole("button", { name: "Run Forex research" });
    fireEvent.click(runButton);

    const review = await screen.findByRole("button", { name: "Review for activation" });
    expect(screen.getByText("Score 0.81").textContent).toBe("Score 0.81");
    fireEvent.click(review);
    fireEvent.change(screen.getByLabelText("Reason for this selection"), {
      target: { value: "Highest-ranked eligible forex candidate" }
    });
    fireEvent.click(screen.getByLabelText(/I reviewed the eligibility evidence/i));
    fireEvent.click(screen.getByRole("button", { name: "Approve active market" }));

    await waitFor(() => {
      expect(screen.getByText(/EURUSD is now the human-approved forex market/i)).toBeTruthy();
    });
    const activation = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith("/markets/active/FOREX") && init?.method === "PUT"
    );
    expect(activation).toBeTruthy();
    expect(JSON.parse(String(activation?.[1]?.body))).toMatchObject({
      candidate_assessment_id: "candidate-1",
      confirmation: "CONFIRMED",
      replace: false
    });
  });
});
