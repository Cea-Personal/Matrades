"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { CoordinatedMarketResearchReport } from "@/lib/api/generated";

import { ActiveMarkets, type ActiveMarket } from "./ActiveMarkets";
import { InstrumentLibrary, type InstrumentCategory, type MarketInstrument } from "./InstrumentLibrary";
import { MarketResearchControls } from "./MarketResearchControls";
import { MarketResearchReport, type MarketCandidate } from "./MarketResearchReport";
import { MarketRotation } from "./MarketRotation";
type MarketCategory = InstrumentCategory;

type ApiProblem = { detail?: string; title?: string };

function problemMessage(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not complete the market operation.";
}

async function readJson<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

export function MarketsWorkspace() {
  const [category, setCategory] = useState<MarketCategory>("FOREX");
  const [instruments, setInstruments] = useState<MarketInstrument[]>([]);
  const [activeMarkets, setActiveMarkets] = useState<ActiveMarket[]>([]);
  const [coordinatedReport, setCoordinatedReport] = useState<CoordinatedMarketResearchReport>();
  const [candidate, setCandidate] = useState<MarketCandidate>();
  const [deactivation, setDeactivation] = useState<ActiveMarket>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const approvalRef = useRef<HTMLElement>(null);

  const loadEvidence = useCallback(async (selectedCategory: MarketCategory) => {
    try {
      const [libraryResponse, activeResponse] = await Promise.all([
        fetch(`/api/v1/markets/instruments?category=${selectedCategory}`, { credentials: "same-origin" }),
        fetch("/api/v1/markets/active", { credentials: "same-origin" })
      ]);
      if (!libraryResponse.ok || !activeResponse.ok) {
        throw new Error("market evidence unavailable");
      }
      const library = await readJson<{ items: MarketInstrument[] }>(libraryResponse);
      const active = await readJson<{ items: ActiveMarket[] }>(activeResponse);
      setInstruments(library.items);
      setActiveMarkets(active.items);
      setError(undefined);
    } catch {
      setError("TraderX could not load market evidence. Refresh the workspace and try again.");
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(() => loadEvidence(category));
  }, [category, loadEvidence]);

  useEffect(() => {
    if (candidate) approvalRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [candidate]);

  async function retryPinnedAnalysis(runId: string) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/research/category-runs/${runId}/llm-analysis/retry`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Idempotency-Key": crypto.randomUUID() }
      });
      const result = await readJson<{ state?: string; dispatch_state?: string } & ApiProblem>(response);
      if (!response.ok) { setError(problemMessage(result)); return; }
      setCoordinatedReport((current) => current ? {
        ...current,
        categories: current.categories.map((category) => category.run_id === runId ? {
          ...category,
          llm_analysis: { ...category.llm_analysis, state: result.state ?? "RETRY_QUEUED", retry_eligible: false }
        } : category)
      } : current);
      setMessage(result.dispatch_state === "QUEUED_FOR_RECOVERY" ? "Advisory retry was recorded and will run on the scheduler’s next recovery scan." : "Advisory analysis retry was dispatched with the same pinned model. Deterministic results remain unchanged.");
    } catch {
      setError("TraderX could not queue the same-model analysis retry.");
    } finally { setBusy(false); }
  }

  function reviewCandidate(selected: MarketCandidate) {
    if (selected.category) setCategory(selected.category);
    setDeactivation(undefined);
    setCandidate(selected);
  }

  async function requestInstrumentActivation(instrument: MarketInstrument) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/markets/instruments/${instrument.id}/activation-candidate`, {
        credentials: "same-origin"
      });
      const result = await readJson<MarketCandidate & ApiProblem>(response);
      if (!response.ok) {
        setError(problemMessage(result));
        return;
      }
      reviewCandidate(result);
      setMessage(`Review ${result.symbol} for explicit activation. TraderX will preserve the current active market until you confirm.`);
    } catch {
      setError("TraderX could not load current eligibility evidence for this instrument.");
    } finally {
      setBusy(false);
    }
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
      window.dispatchEvent(new Event("traderx:dashboard-refresh"));
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
      window.dispatchEvent(new Event("traderx:dashboard-refresh"));
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
        onReport={(completed) => { setCoordinatedReport(completed); }}
        onStatus={(statusMessage, isError = false) => { if (isError) { setError(statusMessage); setMessage(undefined); } else { setMessage(statusMessage); setError(undefined); } }}
      />
      {coordinatedReport ? <MarketResearchReport coordinated={coordinatedReport} onRetry={(runId) => void retryPinnedAnalysis(runId)} onReview={reviewCandidate} /> : null}
      <ActiveMarkets assignments={activeMarkets} onDeactivate={(assignment) => { setCandidate(undefined); setDeactivation(assignment); }} />
      <InstrumentLibrary busy={busy} category={category} instruments={instruments} onCategoryChange={(nextCategory) => { setCategory(nextCategory); setCandidate(undefined); }} onRequestActivation={(instrument) => void requestInstrumentActivation(instrument)} />
      <MarketRotation />

      {candidate ? (
        <section className="market-approval" aria-labelledby="market-approval-heading" ref={approvalRef} tabIndex={-1}>
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
