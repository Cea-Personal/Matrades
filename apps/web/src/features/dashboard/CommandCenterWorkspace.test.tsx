import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandCenterWorkspace } from "./CommandCenterWorkspace";

function json(body: object): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("CommandCenterWorkspace", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("exposes a usable governed workflow in every phase-four-through-eleven tab", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/integrations")) return json([]);
      if (path.includes("/markets/instruments")) return json({ items: [] });
      if (path.endsWith("/markets/active")) return json({ items: [{ id: "active-1", instrument_id: "instrument-1", symbol: "EURUSD", category: "FOREX", state: "ACTIVE", etag: '"active-1"' }] });
      if (path.includes("/market-rotation/recommendations")) return json({ items: [] });
      if (path.endsWith("/strategies")) return json({ items: [] });
      if (path.endsWith("/validation/runs")) return json({ items: [] });
      if (path.endsWith("/paper/runs")) return json({ items: [] });
      if (path.endsWith("/opportunities")) return json({ items: [] });
      if (path.endsWith("/positions")) return json({ items: [] });
      if (path.endsWith("/journal/entries")) return json({ items: [] });
      if (path.includes("/journal/analytics")) return json({ dimension: "instrument", entry_count: 0, groups: {} });
      if (path.endsWith("/jobs")) return json({ items: [] });
      if (path.endsWith("/notifications/inbox")) return json({ items: [] });
      if (path.endsWith("/notifications/preferences")) return json({ items: [] });
      if (path.endsWith("/operations/health")) return json({ status: "DEGRADED", components: {}, safety_impact: ["account_data"], circuit_breakers: [], secrets_redacted: true });
      if (path.includes("/operations/audit")) return json({ items: [] });
      return json({ items: [] });
    }));

    render(<CommandCenterWorkspace account={{ id: "account-1", name: "Primary", mode: "DEMO", currency: "USD", starting_balance: "100000", status: "ACTIVE", version: 1, etag: '"account-1"', prop_profile_configured: true, risk_policy_configured: true }} onAccountChanged={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Markets" }));
    expect(await screen.findByRole("button", { name: "Run Forex research" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Strategies" }));
    expect(await screen.findByRole("button", { name: "Save immutable draft" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Paper trading" }));
    expect(await screen.findByRole("button", { name: "Run paper evaluation" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Opportunities" }));
    expect(await screen.findByRole("button", { name: "Evaluate current opportunities" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Trade monitoring" }));
    expect(await screen.findByRole("button", { name: "Refresh from MT5" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Journal" }));
    expect(await screen.findByRole("button", { name: "Update from completed activity" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Operations" }));
    expect(await screen.findByRole("heading", { name: "Background jobs" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Notification inbox and delivery" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "System health and append-only audit" })).toBeTruthy();
  });
});
