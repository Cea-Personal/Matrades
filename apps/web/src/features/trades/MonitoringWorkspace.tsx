"use client";

import { useCallback, useEffect, useState } from "react";

import { Positions, type PositionEvidence } from "./Positions";
import { TradeMonitor, type ThesisEvidence } from "./TradeMonitor";

export function MonitoringWorkspace() {
  const [positions, setPositions] = useState<PositionEvidence[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [thesis, setThesis] = useState<ThesisEvidence>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/positions", { credentials: "same-origin" });
      if (!response.ok) throw new Error("unavailable");
      const items = (await response.json() as { items: PositionEvidence[] }).items;
      setPositions(items);
      if (!selectedId && items[0]) setSelectedId(items[0].id);
      setError(undefined);
    } catch { setError("TraderX could not load broker positions."); }
  }, [selectedId]);

  useEffect(() => {
    void Promise.resolve().then(load);
    // Initial external data load only; actions refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    void fetch(`/api/v1/positions/${selectedId}/thesis`, { credentials: "same-origin" })
      .then(async (response) => { if (!response.ok) throw new Error("unavailable"); setThesis(await response.json() as ThesisEvidence); })
      .catch(() => setError("TraderX could not load the frozen thesis."));
  }, [selectedId]);

  async function refresh() {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/positions/refresh", { method: "POST", credentials: "same-origin" });
      const payload = await response.json() as { detail?: string; accounts_refreshed?: number };
      if (!response.ok) { setError(payload.detail ?? "Broker refresh failed closed."); return; }
      setMessage(`Read-only broker refresh completed for ${payload.accounts_refreshed ?? 0} account(s).`);
      await load();
    } catch { setError("TraderX could not refresh the read-only MT5 snapshot."); }
    finally { setBusy(false); }
  }

  async function correct(position: PositionEvidence, classification: string, reason: string) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/positions/${position.id}/classification`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "If-Match": position.etag, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ classification, reason, recommendation_id: classification === "RECOMMENDED" ? position.matched_recommendation_id : null }) });
      const payload = await response.json() as { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Classification correction was rejected."); return; }
      setMessage("The audited classification correction was recorded and shared risk remains inclusive of the position.");
      await load();
    } catch { setError("TraderX could not record the classification correction."); }
    finally { setBusy(false); }
  }

  function select(id: string) {
    if (id !== selectedId) setThesis(undefined);
    setSelectedId(id);
  }
  return <div className="governed-workspace"><Positions busy={busy} onCorrect={correct} onRefresh={refresh} onSelect={select} positions={positions} selectedId={selectedId} /><TradeMonitor thesis={thesis} />{message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</div>;
}
