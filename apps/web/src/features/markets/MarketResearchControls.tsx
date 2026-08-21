"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { CoordinatedMarketResearchReport, MarketResearchModelConfiguration, MarketResearchSchedule } from "@/lib/api/generated";

type Integration = { id: string; provider: string; category: string; state?: string; status?: string };
type Dashboard = { account?: { id: string } | null };

const providerLabels: Record<string, string> = { LITELLM_PROXY: "LiteLLM Gateway" };
const defaultResearchBrief = "Assess volatility, liquidity, material risks, and macro context for each governed market category.";

function responseEtag(response: Response, resource: string, version?: number): string {
  return response.headers.get("ETag") ?? `"${resource}-${version ?? 0}"`;
}

export function MarketResearchControls({ onReport, onStatus }: { onReport: (report: CoordinatedMarketResearchReport) => void; onStatus: (message: string, error?: boolean) => void }) {
  const [accountId, setAccountId] = useState("");
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [scheduleEtag, setScheduleEtag] = useState('"market-research-schedule-0"');
  const [modelEtag, setModelEtag] = useState('"market-research-model-0"');
  const [modelProvider, setModelProvider] = useState("");
  const [exactModelId, setExactModelId] = useState("");
  const [researchBrief, setResearchBrief] = useState("");
  const [intervalHours, setIntervalHours] = useState("24");
  const [anchor, setAnchor] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [enabled, setEnabled] = useState(false);
  const [reason, setReason] = useState("");
  const [nextRun, setNextRun] = useState<string>();
  const [lastRun, setLastRun] = useState<string | null>();
  const [history, setHistory] = useState<CoordinatedMarketResearchReport[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [dashboardResponse, integrationsResponse, scheduleResponse, modelResponse, historyResponse] = await Promise.all([
        fetch("/api/v1/dashboard", { credentials: "same-origin" }),
        fetch("/api/v1/integrations/non-broker", { credentials: "same-origin" }),
        fetch("/api/v1/markets/research/schedule", { credentials: "same-origin" }),
        fetch("/api/v1/markets/research/model-configuration", { credentials: "same-origin" }),
        fetch("/api/v1/markets/research/coordinated", { credentials: "same-origin" })
      ]);
      if ([dashboardResponse, integrationsResponse, scheduleResponse, modelResponse, historyResponse].some((response) => !response.ok)) throw new Error("unavailable");
      const dashboard = await dashboardResponse.json() as Dashboard;
      const integrationPayload = await integrationsResponse.json() as Integration[] | { items: Integration[] };
      const schedule = await scheduleResponse.json() as MarketResearchSchedule;
      const configuredModel = await modelResponse.json() as MarketResearchModelConfiguration;
      const priorRuns = await historyResponse.json() as { items: CoordinatedMarketResearchReport[] };
      setAccountId(dashboard.account?.id ?? "");
      setIntegrations(Array.isArray(integrationPayload) ? integrationPayload : integrationPayload.items);
      setScheduleEtag(responseEtag(scheduleResponse, "market-research-schedule", schedule.version));
      setModelEtag(responseEtag(modelResponse, "market-research-model", configuredModel.version));
      if (schedule.configured !== false && schedule.interval_seconds) {
        setIntervalHours(String(schedule.interval_seconds / 3600));
        setAnchor(schedule.anchored_start_local?.slice(0, 16) ?? "");
        setTimezone(schedule.account_timezone ?? "UTC");
        setEnabled(schedule.enabled);
        setNextRun(schedule.next_run_at);
        setLastRun(schedule.last_due_at);
      }
      if (configuredModel.provider_key && configuredModel.exact_model_id) {
        setModelProvider(configuredModel.provider_key);
        setExactModelId(configuredModel.exact_model_id);
        // Configurations created before research briefs were introduced can be
        // valid database records but invalid form values.  Give those records a
        // safe, advisory-only starting brief so the schedule remains editable.
        setResearchBrief(configuredModel.research_brief?.trim() || defaultResearchBrief);
      }
      setHistory(priorRuns.items);
      setError(undefined);
    } catch {
      setError("TraderX could not load market research automation settings.");
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const availableProviders = useMemo(() => Array.from(new Set(
    integrations
      .filter((integration) => integration.provider === "LITELLM_PROXY" && integration.category === "LLM" && (integration.state === "HEALTHY" || integration.status === "HEALTHY"))
      .map((integration) => integration.provider)
  )).map((value) => ({ value, label: providerLabels[value] ?? value.replaceAll("_", " ") })), [integrations]);
  const effectiveProvider = availableProviders.some((provider) => provider.value === modelProvider)
    ? modelProvider
    : (availableProviders[0]?.value ?? "");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const provider = effectiveProvider;
    const exactModel = exactModelId.trim();
    const brief = researchBrief.trim();
    const trimmedReason = reason.trim();
    const intervalSeconds = Math.round(Number(intervalHours) * 3600);
    const integration = integrations.find((item) => item.provider === provider && item.category === "LLM" && (item.state === "HEALTHY" || item.status === "HEALTHY"));
    if (!accountId) { setError("Configure the trading account before scheduling market research."); return; }
    if (!integration) { setError("Connect and qualify an advisory-model provider in Integrations first."); return; }
    if (!exactModel) { setError("Enter the exact model ID that your selected provider makes available to your credential."); return; }
    if (brief.length < 8) { setError("Add a research brief of at least 8 characters before saving."); return; }
    if (!anchor || Number.isNaN(new Date(anchor).getTime())) { setError("Choose a valid first-run date and time before saving."); return; }
    if (!Number.isFinite(intervalSeconds) || intervalSeconds < 3600 || intervalSeconds > 2592000) { setError("Choose an interval between 1 hour and 30 days."); return; }
    if (trimmedReason.length < 8) { setError("Add a reason of at least 8 characters for this settings change."); return; }
    setBusy(true); setError(undefined);
    let modelSaved = false;
    try {
      const commonHeaders = { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() };
      const modelResponse = await fetch("/api/v1/markets/research/model-configuration", {
        method: "PUT", credentials: "same-origin", headers: { ...commonHeaders, "If-Match": modelEtag },
        body: JSON.stringify({ llm_integration_id: integration.id, provider_key: provider, exact_model_id: exactModel, research_brief: brief, reason: trimmedReason })
      });
      const modelResult = await modelResponse.json() as MarketResearchModelConfiguration & { detail?: string };
      if (!modelResponse.ok) throw new Error(modelResult.detail ?? "The model setting was rejected.");
      modelSaved = true;
      setModelEtag(responseEtag(modelResponse, "market-research-model", modelResult.version));
      const scheduleResponse = await fetch("/api/v1/markets/research/schedule", {
        method: "PUT", credentials: "same-origin", headers: { ...commonHeaders, "Idempotency-Key": crypto.randomUUID(), "If-Match": scheduleEtag },
        body: JSON.stringify({ account_id: accountId, interval_seconds: intervalSeconds, anchored_start_local: new Date(anchor).toISOString(), account_timezone: timezone, enabled, reason: trimmedReason })
      });
      const schedule = await scheduleResponse.json() as MarketResearchSchedule & { detail?: string };
      if (!scheduleResponse.ok) throw new Error(schedule.detail ?? "The schedule setting was rejected.");
      setScheduleEtag(responseEtag(scheduleResponse, "market-research-schedule", schedule.version));
      setNextRun(schedule.next_run_at); setLastRun(schedule.last_due_at);
      setReason("");
      onStatus(enabled ? "Research settings saved. The selected model applies to future runs only." : "Research settings saved, but recurring runs are currently disabled. Enable them when you are ready.");
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "TraderX could not save the research settings.";
      setError(modelSaved ? `The model settings were saved, but the schedule was not: ${detail}` : detail);
    } finally { setBusy(false); }
  }

  async function runAll() {
    if (!accountId) { setError("Configure the trading account before running research."); return; }
    setBusy(true); setError(undefined);
    try {
      const startedResponse = await fetch("/api/v1/markets/research/coordinated", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ account_id: accountId, methodology_version: "market-suitability-v2" })
      });
      const started = await startedResponse.json() as { run_id?: string; detail?: string };
      if (!startedResponse.ok || !started.run_id) throw new Error(started.detail ?? "The coordinated run did not start.");
      let report: (CoordinatedMarketResearchReport & { detail?: string }) | undefined;
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const reportResponse = await fetch(`/api/v1/markets/research/coordinated/${started.run_id}`, { credentials: "same-origin" });
        report = await reportResponse.json() as CoordinatedMarketResearchReport & { detail?: string };
        if (!reportResponse.ok) throw new Error(report.detail ?? "The coordinated report is unavailable.");
        if (["COMPLETED", "PARTIAL", "FAILED"].includes(report.state)) break;
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      if (!report) throw new Error("The coordinated report is unavailable.");
      const completedReport = report;
      onReport(completedReport);
      setHistory((current) => [completedReport, ...current.filter((item) => item.id !== completedReport.id)]);
      onStatus(["COMPLETED", "PARTIAL", "FAILED"].includes(completedReport.state) ? "All three category runs finished. Rankings remain proposals until human activation." : "The coordinated run continues safely in the background. You can close the browser and return to its history.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "TraderX could not run coordinated market research.");
    } finally { setBusy(false); }
  }

  return <section aria-labelledby="market-research-automation"><p className="section-kicker">Browser-independent schedule</p><h3 id="market-research-automation">Market research automation</h3><p>Each run evaluates Commodity, Forex, and Cryptocurrency together, then returns one governed result for each category. The LLM explains evidence only; deterministic gates and ranking retain authority.</p><form className="setup-form" noValidate onSubmit={save}><label htmlFor="research-provider">AI provider<select id="research-provider" onChange={(event) => setModelProvider(event.target.value)} required value={effectiveProvider}>{availableProviders.length === 0 ? <option value="">Qualify LiteLLM Gateway first</option> : availableProviders.map((provider) => <option key={provider.value} value={provider.value}>{provider.label}</option>)}</select></label><label htmlFor="research-model-id">Model ID<input id="research-model-id" maxLength={128} onChange={(event) => setExactModelId(event.target.value)} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}" placeholder="Configured LiteLLM model alias" required value={exactModelId} /></label><label htmlFor="research-brief">Research brief<textarea id="research-brief" maxLength={4000} minLength={8} onChange={(event) => setResearchBrief(event.target.value)} placeholder="Focus the advisory analysis on the market context, risks, and questions that matter to you." required value={researchBrief} /></label><p className="field-hint">This guides the LLM’s advisory explanation only. It is versioned, pinned to future runs, and cannot override eligibility gates, ranking, or activation controls.</p><label htmlFor="research-interval">Run every (hours)<input id="research-interval" min="1" max="720" onChange={(event) => setIntervalHours(event.target.value)} required step="0.25" type="number" value={intervalHours} /></label><p className="field-hint">Minimum one hour. This single interval applies to all three categories in the same coordinated run.</p><label htmlFor="research-anchor">First run at<input id="research-anchor" onChange={(event) => setAnchor(event.target.value)} required type="datetime-local" value={anchor} /></label><label htmlFor="research-timezone">Account time zone<input id="research-timezone" onChange={(event) => setTimezone(event.target.value)} required value={timezone} /></label><label className="confirmation-check" htmlFor="research-enabled"><input checked={enabled} id="research-enabled" onChange={(event) => setEnabled(event.target.checked)} type="checkbox" /> Enable recurring coordinated research</label><label htmlFor="research-reason">Reason for research settings<textarea id="research-reason" minLength={8} onChange={(event) => setReason(event.target.value)} required value={reason} /></label><p className="field-hint">A research brief and an audit reason (at least 8 characters each) are required. If recurring research is unchecked, the settings save but no scheduled run will be created.</p><div className="integration-form-actions"><button disabled={busy} type="submit">{busy ? "Saving…" : "Save coordinated research settings"}</button><button className="secondary-button" disabled={busy} onClick={() => void runAll()} type="button">Run all three categories now</button></div></form><dl className="evidence-metrics"><div><dt>Next coordinated run</dt><dd>{nextRun ? new Date(nextRun).toLocaleString() : "Not scheduled"}</dd></div><div><dt>Last coordinated run</dt><dd>{lastRun ? new Date(lastRun).toLocaleString() : "Not run"}</dd></div><div><dt>Results per run</dt><dd>One result each for Commodity, Forex, and Cryptocurrency</dd></div><div><dt>Overlap policy</dt><dd>Skip; no catch-up</dd></div></dl><section aria-labelledby="research-run-history"><h4 id="research-run-history">Coordinated run history</h4>{history.length ? <ol className="timeline">{history.map((item) => <li key={item.id}><strong>{item.state} · {item.trigger}</strong><span>{item.categories.map((category) => `${category.category}: ${category.outcome}`).join(" · ")}</span><button className="secondary-button" onClick={() => onReport(item)} type="button">View run</button></li>)}</ol> : <p className="workspace-notice">No coordinated market-research run has been recorded yet.</p>}</section>{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</section>;
}
