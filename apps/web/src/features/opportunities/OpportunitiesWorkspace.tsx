"use client";

import { useCallback, useEffect, useState } from "react";

import { OpportunityBoard, type OpportunityEvidence } from "./OpportunityBoard";
import { RecommendationPanel, type RecommendationEvidence } from "./RecommendationPanel";

export function OpportunitiesWorkspace() {
  const [items, setItems] = useState<OpportunityEvidence[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [recommendation, setRecommendation] = useState<RecommendationEvidence>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/opportunities", { credentials: "same-origin" });
      if (!response.ok) throw new Error("unavailable");
      const loaded = (await response.json() as { items: OpportunityEvidence[] }).items;
      setItems(loaded);
      if (!selectedId && loaded[0]) setSelectedId(loaded[0].id);
      setError(undefined);
    } catch { setError("TraderX could not load current opportunities."); }
  }, [selectedId]);

  useEffect(() => {
    void Promise.resolve().then(load);
    // Initial external data load only; actions refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    void fetch(`/api/v1/opportunities/${selectedId}/recommendation`, { credentials: "same-origin" })
      .then(async (response) => { if (!response.ok) throw new Error("unavailable"); setRecommendation(await response.json() as RecommendationEvidence); })
      .catch(() => setError("TraderX could not load the recommendation evidence."));
  }, [selectedId]);

  async function evaluate() {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/opportunities/evaluate", { method: "POST", credentials: "same-origin", headers: { "Idempotency-Key": crypto.randomUUID() } });
      const payload = await response.json() as { items?: OpportunityEvidence[]; detail?: string };
      if (!response.ok || !payload.items) { setError(payload.detail ?? "Opportunity evaluation failed closed."); return; }
      setItems(payload.items);
      setSelectedId(payload.items[0]?.id ?? "");
      setMessage(payload.items.length ? "Current strategies and markets were evaluated. Risk authorization remains a separate gate." : "No live-approved strategy is attached to an active market yet.");
    } catch { setError("TraderX could not evaluate opportunities."); }
    finally { setBusy(false); }
  }

  function selectOpportunity(id: string) {
    if (id !== selectedId) setRecommendation(undefined);
    setSelectedId(id);
  }

  return <div className="governed-workspace"><OpportunityBoard busy={busy} items={items} onEvaluate={evaluate} onSelect={selectOpportunity} selectedId={selectedId} /><RecommendationPanel recommendation={recommendation} />{message ? <p className="status-message" role="status">{message}</p> : null}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</div>;
}
