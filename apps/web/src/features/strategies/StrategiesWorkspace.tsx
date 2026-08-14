"use client";

import { useCallback, useEffect, useState } from "react";

import { ResearchBacktest, type BacktestEvidence } from "./ResearchBacktest";
import { StrategyBuilder, type StrategyDraft } from "./StrategyBuilder";
import { StrategyVersions, type StrategySummary, type StrategyVersionSummary } from "./StrategyVersions";
import { ValidationReport, type ValidationEvidence } from "./ValidationReport";

type ActiveMarket = { instrument_id: string; symbol: string; category: string };
type ApiProblem = { detail?: string; title?: string };

function problemMessage(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not complete the strategy operation.";
}

async function result<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

export function StrategiesWorkspace() {
  const [markets, setMarkets] = useState<ActiveMarket[]>([]);
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [selected, setSelected] = useState<StrategySummary>();
  const [version, setVersion] = useState<StrategyVersionSummary>();
  const [backtest, setBacktest] = useState<BacktestEvidence>();
  const [backtestJobId, setBacktestJobId] = useState<string>();
  const [validation, setValidation] = useState<ValidationEvidence>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [marketsResponse, strategiesResponse] = await Promise.all([
        fetch("/api/v1/markets/active", { credentials: "same-origin" }),
        fetch("/api/v1/strategies", { credentials: "same-origin" })
      ]);
      if (!marketsResponse.ok || !strategiesResponse.ok) throw new Error("unavailable");
      setMarkets((await result<{ items: ActiveMarket[] }>(marketsResponse)).items);
      const loaded = (await result<{ items: StrategySummary[] }>(strategiesResponse)).items;
      setStrategies(loaded);
      if (selected) {
        const refreshed = loaded.find((item) => item.id === selected.id);
        setSelected(refreshed);
        if (version && refreshed) setVersion(refreshed.versions.find((item) => item.id === version.id));
      }
      setError(undefined);
    } catch {
      setError("TraderX could not load strategy evidence. Refresh and try again.");
    }
  }, [selected, version]);

  useEffect(() => {
    void Promise.resolve().then(load);
    // Initial external data load only; later actions refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveStrategy(draft: StrategyDraft) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const endpoint = selected ? `/api/v1/strategies/${selected.id}/versions` : "/api/v1/strategies";
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
          ...(selected ? { "If-Match": selected.etag } : {})
        },
        body: JSON.stringify(selected
          ? { definition: draft.definition, change_summary: draft.change_summary }
          : draft)
      });
      const saved = await result<(StrategySummary & { created_version?: StrategyVersionSummary }) | StrategyVersionSummary | ApiProblem>(response);
      if (!response.ok) {
        setError(problemMessage(saved as ApiProblem));
        return;
      }
      setBacktest(undefined);
      setValidation(undefined);
      setMessage(selected ? "A new immutable draft version was created." : "Strategy and immutable draft version created.");
      await load();
    } catch {
      setError("TraderX could not save this strategy definition.");
    } finally {
      setBusy(false);
    }
  }

  async function runBacktest(manifestHash?: string) {
    if (!version) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await fetch("/api/v1/validation/backtests", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ strategy_version_id: version.id, manifest_hash: manifestHash })
      });
      const payload = await result<{ run?: BacktestEvidence; job?: { id: string } } & ApiProblem>(response);
      if (!response.ok || !payload.run) {
        setError(problemMessage(payload));
        return;
      }
      setBacktest(payload.run);
      setBacktestJobId(payload.job?.id);
      setValidation(undefined);
      setMessage("Reproducible chronological backtest completed. Validation is still required.");
      await load();
    } catch {
      setError("TraderX could not complete the backtest.");
    } finally {
      setBusy(false);
    }
  }

  async function runValidation() {
    if (!version || !backtest) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await fetch("/api/v1/validation/runs", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ strategy_version_id: version.id, backtest_run_id: backtest.id, seed: 20260813 })
      });
      const payload = await result<{ run?: ValidationEvidence } & ApiProblem>(response);
      if (!response.ok || !payload.run) {
        setError(problemMessage(payload));
        return;
      }
      setValidation(payload.run);
      setMessage(payload.run.state === "PASS" ? "Required validation evidence passed. Paper eligibility may now be reviewed." : "Validation failed. This version cannot progress to paper trading.");
      await load();
    } catch {
      setError("TraderX could not complete validation.");
    } finally {
      setBusy(false);
    }
  }

  function selectStrategy(strategy: StrategySummary) {
    setSelected(strategy);
    setVersion(strategy.versions[0]);
    setBacktest(undefined);
    setBacktestJobId(undefined);
    setValidation(undefined);
  }

  return (
    <div className="strategy-workspace">
      <StrategyBuilder activeMarkets={markets} busy={busy} creatingVersion={Boolean(selected)} onSave={saveStrategy} />
      <StrategyVersions onSelectStrategy={selectStrategy} onSelectVersion={setVersion} selectedStrategyId={selected?.id} selectedVersionId={version?.id} strategies={strategies} />
      <ResearchBacktest backtest={backtest} busy={busy} jobId={backtestJobId} onRunBacktest={runBacktest} selectedVersion={version} />
      <ValidationReport backtest={backtest} busy={busy} onRunValidation={runValidation} validation={validation} />
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
    </div>
  );
}
