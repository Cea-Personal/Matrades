"use client";

import { useCallback, useEffect, useState } from "react";

import { InstrumentReactivation, type ReactivationPlan } from "./InstrumentReactivation";
import { MarketReplacement, type ReplacementEvidence } from "./MarketReplacement";

type Instrument = { id: string; symbol: string; status: string; category: string };

export function MarketRotation() {
  const [recommendations, setRecommendations] = useState<ReplacementEvidence[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [instrumentId, setInstrumentId] = useState("");
  const [plan, setPlan] = useState<ReactivationPlan>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const responses = await Promise.all([
        fetch("/api/v1/market-rotation/recommendations", { credentials: "same-origin" }),
        ...["COMMODITY", "FOREX", "CRYPTO"].map((category) => fetch(`/api/v1/markets/instruments?category=${category}`, { credentials: "same-origin" }))
      ]);
      if (responses.some((response) => !response.ok)) throw new Error("unavailable");
      setRecommendations((await responses[0].json() as { items: ReplacementEvidence[] }).items);
      const library = (await Promise.all(responses.slice(1).map(async (response) => (await response.json() as { items: Instrument[] }).items))).flat();
      setInstruments(library);
      if (!instrumentId && library[0]) setInstrumentId(library[0].id);
      setError(undefined);
    } catch { setError("TraderX could not load rotation and retained-knowledge evidence."); }
  }, [instrumentId]);

  useEffect(() => {
    void Promise.resolve().then(load);
    // Initial external data load only; actions refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function inspect(id: string) {
    setInstrumentId(id); setPlan(undefined); setError(undefined);
    try {
      const response = await fetch(`/api/v1/market-rotation/instruments/${id}/reactivation`, { credentials: "same-origin" });
      const payload = await response.json() as ReactivationPlan & { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Reactivation evidence is unavailable."); return; }
      setPlan(payload);
    } catch { setError("TraderX could not inspect retained knowledge."); }
  }

  async function requestPlan() {
    if (!instrumentId) return;
    setBusy(true); setError(undefined);
    try {
      const response = await fetch(`/api/v1/market-rotation/instruments/${instrumentId}/reactivation`, { method: "POST", credentials: "same-origin", headers: { "Idempotency-Key": crypto.randomUUID() } });
      const payload = await response.json() as ReactivationPlan & { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Reactivation plan was not created."); return; }
      setPlan(payload); setMessage("The refresh/revalidation plan was recorded. The instrument was not automatically reactivated.");
    } catch { setError("TraderX could not create the reactivation plan."); }
    finally { setBusy(false); }
  }

  return <><MarketReplacement recommendations={recommendations} /><InstrumentReactivation busy={busy} instrumentId={instrumentId} instruments={instruments} onInspect={inspect} onRequest={requestPlan} plan={plan} />{message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</>;
}
