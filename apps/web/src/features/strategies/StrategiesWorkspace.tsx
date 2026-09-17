"use client";

import { useCallback, useEffect, useState } from "react";

import { ResearchBacktest, type BacktestEvidence } from "./ResearchBacktest";
import { AiStrategyResearch, type AiStrategyResearchReport, type LiteLlmModelOption } from "./AiStrategyResearch";
import { StrategyVersions, type StrategySummary, type StrategyVersionSummary } from "./StrategyVersions";
import { ValidationReport, type ValidationEvidence } from "./ValidationReport";

type ActiveMarket = { instrument_id: string; symbol: string; category: string };
type ApiProblem = { detail?: string; title?: string };
type LiteLlmModel = { id: string; alias: string; provider_model: string };

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
  const [aiResearch, setAiResearch] = useState<AiStrategyResearchReport>();
  const [modelAliases, setModelAliases] = useState<LiteLlmModelOption[]>([]);
  const [fullModelAlias, setFullModelAlias] = useState("");
  const [manualModelAlias, setManualModelAlias] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [marketsResponse, strategiesResponse, aliasesResponse, latestResearchResponse] = await Promise.all([
        fetch("/api/v1/markets/active", { credentials: "same-origin" }),
        fetch("/api/v1/strategies", { credentials: "same-origin" }),
        fetch("/api/v1/integrations/litellm/models", { credentials: "same-origin" }),
        fetch("/api/v1/strategies/ai-research/latest", { credentials: "same-origin" })
      ]);
      if (!marketsResponse.ok || !strategiesResponse.ok) throw new Error("unavailable");
      setMarkets((await result<{ items: ActiveMarket[] }>(marketsResponse)).items);
      const loaded = (await result<{ items: StrategySummary[] }>(strategiesResponse)).items;
      setStrategies(loaded);
      if (aliasesResponse.ok) {
        const aliases = (await result<{ items?: LiteLlmModel[] }>(aliasesResponse)).items ?? [];
        const values = aliases.map((item) => ({ alias: item.alias, provider_model: item.provider_model || "Model ID unavailable" })).sort((left, right) => left.alias.localeCompare(right.alias));
        setModelAliases(values);
        setFullModelAlias((current) => values.some((item) => item.alias === current) ? current : (values[0]?.alias ?? ""));
        setManualModelAlias((current) => values.some((item) => item.alias === current) ? current : (values[0]?.alias ?? ""));
      }
      if (latestResearchResponse.ok) {
        const latest = await result<{ job: AiStrategyResearchReport["job"] | null; result: AiStrategyResearchReport["result"] | null }>(latestResearchResponse);
        if (latest.job) setAiResearch({ job: latest.job, result: latest.result ?? undefined });
      }
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

  async function startAiResearch() {
    if (!fullModelAlias) {
      setError("Choose a healthy LiteLLM model alias before starting strategy research.");
      return;
    }
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch("/api/v1/strategies/ai-research", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID()
        },
        body: JSON.stringify({ model_alias: fullModelAlias })
      });
      const saved = await result<{ job?: { id: string }; detail?: string } & ApiProblem>(response);
      if (!response.ok) {
        setError(problemMessage(saved as ApiProblem));
        return;
      }
      if (!saved.job?.id) {
        setError("TraderX did not return an AI strategy research job.");
        return;
      }
      setAiResearch({ job: { id: saved.job.id, state: "QUEUED", progress: { message: "Queued" } } });
      setMessage("AI strategy research is queued for all three active markets.");
    } catch {
      setError("TraderX could not start AI strategy research.");
    } finally {
      setBusy(false);
    }
  }

  async function developStrategyIdea(instrumentId: string, description: string) {
    if (!manualModelAlias) {
      setError("Choose a healthy LiteLLM model alias before developing a strategy idea.");
      return;
    }
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch("/api/v1/strategies/ai-research/from-idea", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ instrument_id: instrumentId, description, model_alias: manualModelAlias })
      });
      const saved = await result<{ job?: { id: string } } & ApiProblem>(response);
      if (!response.ok) {
        setError(problemMessage(saved));
        return;
      }
      if (!saved.job?.id) {
        setError("TraderX did not return an AI strategy idea research job.");
        return;
      }
      setAiResearch({ job: { id: saved.job.id, state: "QUEUED", progress: { message: "Queued" } } });
      setMessage("AI is developing your strategy idea into a bounded draft.");
    } catch {
      setError("TraderX could not start AI strategy idea research.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!aiResearch || !["QUEUED", "RUNNING"].includes(aiResearch.job.state)) return;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const response = await fetch(`/api/v1/strategies/ai-research/${aiResearch.job.id}`, { credentials: "same-origin" });
          const report = await result<AiStrategyResearchReport & ApiProblem>(response);
          if (!response.ok) {
            setError(problemMessage(report));
            return;
          }
          setAiResearch(report);
          if (report.job.state === "COMPLETED") {
            setMessage("AI strategy research completed. Review a draft below, then backtest it.");
            await load();
          }
        } catch {
          setError("TraderX could not refresh AI strategy research.");
        }
      })();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [aiResearch?.job.id, aiResearch?.job.state, load]);

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
      <AiStrategyResearch activeMarkets={markets} busy={busy} fullModelAlias={fullModelAlias} manualModelAlias={manualModelAlias} modelAliases={modelAliases} onDevelopIdea={developStrategyIdea} onFullModelAliasChange={setFullModelAlias} onManualModelAliasChange={setManualModelAlias} onResearch={startAiResearch} report={aiResearch} />
      <StrategyVersions onSelectStrategy={selectStrategy} onSelectVersion={setVersion} selectedStrategyId={selected?.id} selectedVersionId={version?.id} strategies={strategies} />
      <ResearchBacktest backtest={backtest} busy={busy} jobId={backtestJobId} onRunBacktest={runBacktest} selectedVersion={version} />
      <ValidationReport backtest={backtest} busy={busy} onRunValidation={runValidation} validation={validation} />
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
    </div>
  );
}
