import { cleanup, render, screen } from "@testing-library/react";
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

  it("uses one coordinated research workflow rather than category-specific runs", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/dashboard")) return json({ account: { id: "account-1" } });
      if (path.endsWith("/integrations/non-broker")) return json({ items: [] });
      if (path.endsWith("/markets/research/schedule")) return json({ configured: false, enabled: false });
      if (path.endsWith("/markets/research/model-configuration")) return json({ configured: false });
      if (path.endsWith("/markets/research/coordinated")) return json({ items: [] });
      if (path.includes("/markets/instruments")) {
        return json({ items: [{ id: "instrument-1", symbol: "EURUSD", display_name: "Euro / US Dollar", category: "FOREX", status: "INACTIVE", data_status: "VERIFIED" }] });
      }
      if (path.endsWith("/markets/active") && (!init?.method || init.method === "GET")) {
        return json({ items: [], maximum: 3 });
      }
      return json({ detail: `Unhandled request ${path}` }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MarketsWorkspace />);
    expect(await screen.findByRole("button", { name: "Run all three categories now" })).toBeTruthy();
    expect(screen.getByLabelText("Run every (hours)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run Forex research" })).toBeNull();
  });
});
