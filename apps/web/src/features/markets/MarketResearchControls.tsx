"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { CoordinatedMarketResearchReport, MarketResearchModelConfiguration, MarketResearchSchedule } from "@/lib/api/generated";

type Integration = { id: string; provider: string; category: string; state?: string; status?: string };
type Dashboard = { account?: { id: string } | null };

const models = [
  { value: "OPENAI_RESPONSES:gpt-5.6-terra", label: "OpenAI · gpt-5.6-terra" },
  { value: "ANTHROPIC_MESSAGES:claude-sonnet-5", label: "Anthropic · claude-sonnet-5" }
];

export function MarketResearchControls({ onReport, onStatus }: { onReport: (report: CoordinatedMarketResearchReport) => void; onStatus: (message: string, error?: boolean) => void }) {
  const [accountId, setAccountId] = useState("");
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [scheduleEtag, setScheduleEtag] = useState('"market-research-schedule-0"');
  const [modelEtag, setModelEtag] = useState('"market-research-model-0"');
  const [model, setModel] = useState(models[0].value);
  const [interval, setInterval] = useState("86400");
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
      setScheduleEtag(scheduleResponse.headers.get("ETag") ?? '"market-research-schedule-0"');
      setModelEtag(modelResponse.headers.get("ETag") ?? '"market-research-model-0"');
      if (schedule.configured !== false && schedule.interval_seconds) {
        setInterval(String(schedule.interval_seconds));
        setAnchor(schedule.anchored_start_local?.slice(0, 16) ?? "");
        setTimezone(schedule.account_timezone ?? "UTC");
        setEnabled(schedule.enabled);
        setNextRun(schedule.next_run_at);
        setLastRun(schedule.last_due_at);
      }
      if (configuredModel.provider_key && configuredModel.exact_model_id) setModel(`${configuredModel.provider_key}:${configuredModel.exact_model_id}`);
      setHistory(priorRuns.items);
      setError(undefined);
    } catch {
      setError("TraderX could not load market research automation settings.");
    }
  }, []);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const availableModels = useMemo(() => models.filter((item) => integrations.some((integration) => {
    const provider = item.value.split(":")[0];
    return integration.provider === provider && integration.category === "LLM" && (integration.state === "HEALTHY" || integration.status === "HEALTHY");
  })), [integrations]);
  const effectiveModel = availableModels.some((item) => item.value === model) ? model : (availableModels[0]?.value ?? "");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const [provider, exactModel] = effectiveModel.split(":");
    const integration = integrations.find((item) => item.provider === provider && item.category === "LLM");
    if (!accountId) { setError("Configure the trading account before scheduling market research."); return; }
    if (!integration) { setError(`Connect and qualify ${provider === "OPENAI_RESPONSES" ? "OpenAI" : "Anthropic"} in Integrations first.`); return; }
    setBusy(true); setError(undefined);
    try {
      const commonHeaders = { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() };
      const modelResponse = await fetch("/api/v1/markets/research/model-configuration", {
        method: "PUT", credentials: "same-origin", headers: { ...commonHeaders, "If-Match": modelEtag },
        body: JSON.stringify({ llm_integration_id: integration.id, provider_key: provider, exact_model_id: exactModel, reason })
      });
      const modelResult = await modelResponse.json() as MarketResearchModelConfiguration & { detail?: string };
      if (!modelResponse.ok) throw new Error(modelResult.detail ?? "The model setting was rejected.");
      setModelEtag(modelResponse.headers.get("ETag") ?? modelEtag);
      const scheduleResponse = await fetch("/api/v1/markets/research/schedule", {
        method: "PUT", credentials: "same-origin", headers: { ...commonHeaders, "Idempotency-Key": crypto.randomUUID(), "If-Match": scheduleEtag },
        body: JSON.stringify({ account_id: accountId, interval_seconds: Number(interval), anchored_start_local: new Date(anchor).toISOString(), account_timezone: timezone, enabled, reason })
      });
      const schedule = await scheduleResponse.json() as MarketResearchSchedule & { detail?: string };
      if (!scheduleResponse.ok) throw new Error(schedule.detail ?? "The schedule setting was rejected.");
      setScheduleEtag(scheduleResponse.headers.get("ETag") ?? scheduleEtag);
      setNextRun(schedule.next_run_at); setLastRun(schedule.last_due_at);
      onStatus("Research settings saved. The selected model applies to future runs only.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "TraderX could not save the research settings.");
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

  return <section aria-labelledby="market-research-automation"><p className="section-kicker">Browser-independent schedule</p><h3 id="market-research-automation">Market research automation</h3><p>One database-owned occurrence coordinates Commodity, Forex, and Cryptocurrency. The LLM explains evidence only; deterministic gates and ranking retain authority.</p><form className="setup-form" onSubmit={save}><label htmlFor="research-model">Global research model<select id="research-model" onChange={(event) => setModel(event.target.value)} required value={effectiveModel}>{availableModels.length === 0 ? <option value="">Qualify OpenAI or Anthropic first</option> : availableModels.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label htmlFor="research-interval">Research interval<input id="research-interval" min="3600" max="2592000" onChange={(event) => setInterval(event.target.value)} required type="number" value={interval} /></label><label htmlFor="research-anchor">Anchor start<input id="research-anchor" onChange={(event) => setAnchor(event.target.value)} required type="datetime-local" value={anchor} /></label><label htmlFor="research-timezone">Account time zone<input id="research-timezone" onChange={(event) => setTimezone(event.target.value)} required value={timezone} /></label><label className="confirmation-check" htmlFor="research-enabled"><input checked={enabled} id="research-enabled" onChange={(event) => setEnabled(event.target.checked)} type="checkbox" /> Enable recurring research</label><label htmlFor="research-reason">Reason for research settings<textarea id="research-reason" minLength={8} onChange={(event) => setReason(event.target.value)} required value={reason} /></label><div className="integration-form-actions"><button disabled={busy || !anchor || !effectiveModel} type="submit">Save research settings</button><button className="secondary-button" disabled={busy} onClick={() => void runAll()} type="button">Run all three categories</button></div></form><dl className="evidence-metrics"><div><dt>Next occurrence</dt><dd>{nextRun ? new Date(nextRun).toLocaleString() : "Not scheduled"}</dd></div><div><dt>Last occurrence</dt><dd>{lastRun ? new Date(lastRun).toLocaleString() : "Not run"}</dd></div><div><dt>Overlap policy</dt><dd>Skip; no catch-up</dd></div></dl><section aria-labelledby="research-run-history"><h4 id="research-run-history">Coordinated run history</h4>{history.length ? <ol className="timeline">{history.map((item) => <li key={item.id}><strong>{item.state} · {item.trigger}</strong><span>{item.categories.map((category) => `${category.category}: ${category.outcome}`).join(" · ")}</span><button className="secondary-button" onClick={() => onReport(item)} type="button">View run</button></li>)}</ol> : <p className="workspace-notice">No coordinated market-research run has been recorded yet.</p>}</section>{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</section>;
}
