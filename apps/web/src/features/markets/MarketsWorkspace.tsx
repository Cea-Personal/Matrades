"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type { CoordinatedMarketResearchReport } from "@/lib/api/generated";

import { ActiveMarkets, type ActiveMarket } from "./ActiveMarkets";
import { InstrumentLibrary, type MarketInstrument, type SpecialistIntegration } from "./InstrumentLibrary";
import { MarketResearchControls } from "./MarketResearchControls";
import { MarketResearchReport, type MarketCandidate } from "./MarketResearchReport";
import { MarketRotation } from "./MarketRotation";

type MarketCategory = "COMMODITY" | "FOREX" | "CRYPTO";

type MarketReport = {
  id: string;
  category: MarketCategory;
  state: string;
  methodology_version: string;
  input_manifest_hash: string;
  completed_at: string | null;
  candidates: MarketCandidate[];
  ranking_is_not_activation: boolean;
};

type ApiProblem = { detail?: string; title?: string };

const categories: Array<{ id: MarketCategory; label: string }> = [
  { id: "COMMODITY", label: "Commodity" },
  { id: "FOREX", label: "Forex" },
  { id: "CRYPTO", label: "Cryptocurrency" }
];

function problemMessage(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not complete the market operation.";
}

async function readJson<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

export function MarketsWorkspace() {
  const [category, setCategory] = useState<MarketCategory>("FOREX");
  const [instruments, setInstruments] = useState<MarketInstrument[]>([]);
  const [specialistIntegrations, setSpecialistIntegrations] = useState<SpecialistIntegration[]>([]);
  const [activeMarkets, setActiveMarkets] = useState<ActiveMarket[]>([]);
  const [report, setReport] = useState<MarketReport>();
  const [coordinatedReport, setCoordinatedReport] = useState<CoordinatedMarketResearchReport>();
  const [candidate, setCandidate] = useState<MarketCandidate>();
  const [deactivation, setDeactivation] = useState<ActiveMarket>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const loadEvidence = useCallback(async (selectedCategory: MarketCategory) => {
    try {
      const [libraryResponse, activeResponse, integrationsResponse] = await Promise.all([
        fetch(`/api/v1/markets/instruments?category=${selectedCategory}`, { credentials: "same-origin" }),
        fetch("/api/v1/markets/active", { credentials: "same-origin" }),
        fetch("/api/v1/integrations/non-broker", { credentials: "same-origin" })
      ]);
      if (!libraryResponse.ok || !activeResponse.ok || !integrationsResponse.ok) {
        throw new Error("market evidence unavailable");
      }
      const library = await readJson<{ items: MarketInstrument[] }>(libraryResponse);
      const active = await readJson<{ items: ActiveMarket[] }>(activeResponse);
      const integrations = await readJson<{ items: SpecialistIntegration[] }>(integrationsResponse);
      setInstruments(library.items);
      setActiveMarkets(active.items);
      setSpecialistIntegrations(integrations.items);
      setError(undefined);
    } catch {
      setError("TraderX could not load market evidence. Refresh the workspace and try again.");
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(() => loadEvidence(category));
  }, [category, loadEvidence]);

  async function runResearch() {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    setCandidate(undefined);
    try {
      const response = await fetch("/api/v1/markets/research", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ category, methodology_version: "market-suitability-v1" })
      });
      const result = await readJson<{ run_id?: string } & ApiProblem>(response);
      if (!response.ok || !result.run_id) {
        setError(problemMessage(result));
        return;
      }
      const reportResponse = await fetch(`/api/v1/markets/research/${result.run_id}`, {
        credentials: "same-origin"
      });
      const completed = await readJson<MarketReport & ApiProblem>(reportResponse);
      if (!reportResponse.ok) {
        setError(problemMessage(completed));
        return;
      }
      setReport(completed);
      setMessage(
        completed.candidates.length
          ? "Research completed. Review every failed gate and ranking before activating a market."
          : "Research completed, but the broker supplied no classifiable candidates for this category."
      );
      await loadEvidence(category);
    } catch {
      setError("TraderX could not run market research. No active market was changed.");
    } finally {
      setBusy(false);
    }
  }

  async function retryPinnedAnalysis(runId: string) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/research/category-runs/${runId}/llm-analysis/retry`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Idempotency-Key": crypto.randomUUID() }
      });
      const result = await readJson<{ state?: string } & ApiProblem>(response);
      if (!response.ok) { setError(problemMessage(result)); return; }
      setMessage("Advisory analysis retry was queued with the same pinned model. Deterministic results remain unchanged.");
    } catch {
      setError("TraderX could not queue the same-model analysis retry.");
    } finally { setBusy(false); }
  }

  async function approveMapping(instrument: MarketInstrument, mapping: { integrationId: string; providerSymbol: string; venue: string; contractVariant?: string; reason: string }) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/instruments/${instrument.id}/mapping`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "If-Match": `"instrument-${instrument.id}-${instrument.version ?? 1}"`, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ integration_id: mapping.integrationId, provider_symbol: mapping.providerSymbol, venue: mapping.venue, contract_variant: mapping.contractVariant, mapping_revision: "owner-mapping-v1", reason: mapping.reason })
      });
      const result = await readJson<{ status?: string } & ApiProblem>(response);
      if (!response.ok) { setError(problemMessage(result)); return; }
      setMessage(`${instrument.symbol} now has an approved specialist mapping. The next run will still verify entitlement, freshness, and every deterministic gate.`);
      await loadEvidence(category);
    } catch { setError("TraderX could not approve the specialist symbol mapping."); }
    finally { setBusy(false); }
  }

  function reviewCandidate(selected: MarketCandidate) {
    if (selected.category) setCategory(selected.category);
    setDeactivation(undefined);
    setCandidate(selected);
  }

  async function approveCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidate) return;
    const form = new FormData(event.currentTarget);
    const current = activeMarkets.find((assignment) => assignment.category === category);
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/active/${category}`, {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
          "If-Match": current?.etag ?? `"active-${category}-0"`
        },
        body: JSON.stringify({
          candidate_assessment_id: candidate.id,
          replace: Boolean(current && current.symbol !== candidate.symbol),
          confirmation: form.get("market-confirmation") === "on" ? "CONFIRMED" : "",
          reason: form.get("market-reason")
        })
      });
      const result = await readJson<ActiveMarket & ApiProblem>(response);
      if (!response.ok) {
        setError(problemMessage(result));
        return;
      }
      setCandidate(undefined);
      setMessage(`${result.symbol} is now the human-approved ${category.toLowerCase()} market.`);
      await loadEvidence(category);
    } catch {
      setError("TraderX could not approve this market. The current active market was preserved.");
    } finally {
      setBusy(false);
    }
  }

  async function deactivateMarket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!deactivation) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/active/${deactivation.category}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
          "If-Match": deactivation.etag
        },
        body: JSON.stringify({ confirmation: "DEACTIVATE", reason: form.get("deactivation-reason") })
      });
      const result = await readJson<{ deactivated?: boolean } & ApiProblem>(response);
      if (!response.ok || !result.deactivated) {
        setError(problemMessage(result));
        return;
      }
      setMessage(`${deactivation.symbol} was deactivated. TraderX did not select a replacement.`);
      setDeactivation(undefined);
      await loadEvidence(category);
    } catch {
      setError("TraderX could not deactivate this market. The current assignment was preserved.");
    } finally {
      setBusy(false);
    }
  }

  const current = activeMarkets.find((assignment) => assignment.category === category);

  return (
    <div className="market-workspace">
      <MarketResearchControls
        onReport={(completed) => { setCoordinatedReport(completed); setReport(undefined); }}
        onStatus={(statusMessage, isError = false) => { if (isError) { setError(statusMessage); setMessage(undefined); } else { setMessage(statusMessage); setError(undefined); } }}
      />
      {coordinatedReport ? <MarketResearchReport coordinated={coordinatedReport} onRetry={(runId) => void retryPinnedAnalysis(runId)} onReview={reviewCandidate} /> : null}
      <section aria-labelledby="market-category-heading">
        <p className="section-kicker">Active universe</p>
        <h3 id="market-category-heading">Research one governed market category</h3>
        <p>Broker and data gates are evaluated before volatility and suitability ranking. Research never changes an active market.</p>
        <div className="market-category-tabs" role="group" aria-label="Market category">
          {categories.map((item) => (
            <button
              aria-pressed={category === item.id}
              className={category === item.id ? "active" : "secondary-button"}
              key={item.id}
              onClick={() => { setCategory(item.id); setReport(undefined); setCandidate(undefined); }}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
        <button disabled={busy} onClick={runResearch} type="button">
          {busy ? "Evaluating evidence…" : `Run ${categories.find((item) => item.id === category)?.label} research`}
        </button>
      </section>

      <ActiveMarkets assignments={activeMarkets} onDeactivate={(assignment) => { setCandidate(undefined); setDeactivation(assignment); }} />
      <InstrumentLibrary busy={busy} instruments={instruments} integrations={specialistIntegrations} onApproveMapping={(instrument, mapping) => void approveMapping(instrument, mapping)} onRunResearch={runResearch} />
      {report ? <MarketResearchReport candidates={report.candidates} methodologyVersion={report.methodology_version} onReview={reviewCandidate} /> : null}
      <MarketRotation />

      {candidate ? (
        <section className="market-approval" aria-labelledby="market-approval-heading">
          <p className="section-kicker">Human approval</p>
          <h3 id="market-approval-heading">{current ? `Replace ${current.symbol} with ${candidate.symbol}?` : `Activate ${candidate.symbol}?`}</h3>
          <p>This changes which {category.toLowerCase()} market may participate in live opportunity ranking. It never places an order.</p>
          <form className="setup-form" onSubmit={approveCandidate}>
            <label htmlFor="market-reason">Reason for this selection<textarea id="market-reason" name="market-reason" minLength={8} required /></label>
            <label className="confirmation-check" htmlFor="market-confirmation"><input id="market-confirmation" name="market-confirmation" required type="checkbox" /> I reviewed the eligibility evidence, ranking, and effect on the active slot.</label>
            <div className="integration-form-actions">
              <button disabled={busy} type="submit">{busy ? "Recording…" : current ? "Approve replacement" : "Approve active market"}</button>
              <button className="secondary-button" disabled={busy} onClick={() => setCandidate(undefined)} type="button">Cancel</button>
            </div>
          </form>
        </section>
      ) : null}

      {deactivation ? (
        <section className="market-approval" aria-labelledby="market-deactivation-heading">
          <p className="section-kicker">Human deactivation</p>
          <h3 id="market-deactivation-heading">Deactivate {deactivation.symbol}?</h3>
          <p>The {deactivation.category.toLowerCase()} slot will remain empty until a separately reviewed candidate is approved.</p>
          <form className="setup-form" onSubmit={deactivateMarket}>
            <label htmlFor="deactivation-reason">Reason for deactivation<textarea id="deactivation-reason" name="deactivation-reason" minLength={8} required /></label>
            <div className="integration-form-actions">
              <button className="danger-button" disabled={busy} type="submit">{busy ? "Recording…" : "Confirm deactivation"}</button>
              <button className="secondary-button" disabled={busy} onClick={() => setDeactivation(undefined)} type="button">Keep active</button>
            </div>
          </form>
        </section>
      ) : null}

      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
    </div>
  );
}
