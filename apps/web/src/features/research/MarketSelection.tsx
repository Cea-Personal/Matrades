"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type Fingerprint = {
  regime: string;
  trend_score: number;
  volatility_score: number;
  liquidity_score: number;
  spread_score: number;
  data_quality: number;
  source: string;
  observed_at: string;
};
type Candidate = {
  instrument: string;
  category: string;
  score: number;
  evidence: string[];
  agent_evidence: string[];
  fingerprint: Fingerprint;
};
type AccountSchedule = {
  account_id: string;
  enabled: boolean;
  run_at: string;
  timezone: string;
  weekdays: number[];
  next_run_at: string | null;
};
type ResearchArtifact = { run_id: string; cycle_type: string; state: string; completed_at: string; relative_path: string; checksum: string };

const categories = ["FOREX", "METAL", "CRYPTO"];

export function MarketSelection() {
  const queryClient = useQueryClient();
  const runs = useQuery<Resource[]>({
    queryKey: ["research", "runs"],
    queryFn: () => api("/research/runs"),
    refetchInterval: query => ["QUEUED", "RESEARCHING"].includes(String(query.state.data?.[0]?.state)) ? 3000 : 15000,
  });
  const selections = useQuery<Resource[]>({ queryKey: ["research", "selections"], queryFn: () => api("/research/selections") });
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const artifacts = useQuery<ResearchArtifact[]>({ queryKey: ["research", "artifacts"], queryFn: () => api("/research/artifacts") });
  const [accountId, setAccountId] = useState("");
  const [replacements, setReplacements] = useState<Record<string, string>>({});
  const [scheduleDraft, setScheduleDraft] = useState<AccountSchedule | null>(null);
  const [message, setMessage] = useState("");
  const selectedAccountId = accountId || accounts.data?.[0]?.id || "";
  const accountSchedule = useQuery<AccountSchedule>({
    queryKey: ["configuration", "account", selectedAccountId, "research-schedule"],
    queryFn: () => api(`/configuration/accounts/${selectedAccountId}/research-schedule`),
    enabled: Boolean(selectedAccountId),
  });
  const editableSchedule = scheduleDraft?.account_id === selectedAccountId ? scheduleDraft : accountSchedule.data;

  const latest = runs.data?.find(item => String(item.account_id) === selectedAccountId);
  const candidates = (latest?.candidates as Candidate[] | undefined) ?? [];
  const refresh = async () => { await queryClient.invalidateQueries({ queryKey: ["research"] }); };
  const run = useMutation({
    mutationFn: () => api<Resource>("/research/runs", {
      method: "POST",
      body: JSON.stringify({ account_id: selectedAccountId, market_categories: categories }),
    }),
    onSuccess: async () => { setMessage("Autonomous research queued. Discovery and agent review run in the background."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const decide = useMutation({
    mutationFn: (payload: Record<string, string>) => api(`/research/runs/${latest?.id}/decisions`, { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: async () => { setMessage("HIL-1 decision recorded."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const saveSchedule = useMutation({
    mutationFn: () => {
      if (!editableSchedule) throw new Error("Select a trading account first");
      const { enabled, run_at, timezone, weekdays } = editableSchedule;
      return api<AccountSchedule>(`/configuration/accounts/${selectedAccountId}/research-schedule`, {
        method: "PUT",
        body: JSON.stringify({ enabled, run_at, timezone, weekdays }),
      });
    },
    onSuccess: async result => { setScheduleDraft(result); setMessage("Research schedule saved for this trading account."); await queryClient.invalidateQueries({ queryKey: ["configuration", "account", selectedAccountId, "research-schedule"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const changeSchedule = (patch: Partial<AccountSchedule>) => {
    if (editableSchedule) setScheduleDraft({ ...editableSchedule, ...patch });
  };

  const nextRun = editableSchedule?.next_run_at ? new Date(editableSchedule.next_run_at).toLocaleString() : "Schedule disabled";
  const degradedReasons = (latest?.degraded_reasons as string[] | undefined) ?? [];
  const missingCategories = (latest?.missing_categories as string[] | undefined) ?? [];

  return <section className="section-stack">
    <header>
      <p className="eyebrow">Human-in-the-loop 1</p>
      <h1>Autonomous market research</h1>
      <p className="muted">The Forex, metals, and crypto research agents discover and rank their configured universes. You review one evidence-backed candidate from each category.</p>
    </header>

    <article className="card form-stack">
      <div><h2>Per-account research cycle</h2><p className="muted">The scheduler checks each account every minute. Next scheduled cycle for this account: {nextRun} ({editableSchedule?.timezone ?? "UTC"})</p></div>
      <label>Trading account<select value={selectedAccountId} onChange={event => setAccountId(event.target.value)}>
        {!accounts.data?.length && <option value="">Configure an account first</option>}
        {accounts.data?.map(account => <option key={account.id} value={account.id}>{String(account.name)}</option>)}
      </select></label>
      {editableSchedule ? <>
        <div className="form-grid"><label>Run time<input type="time" value={editableSchedule.run_at} onChange={event => changeSchedule({ run_at: event.target.value })} /></label><label>Timezone<input value={editableSchedule.timezone} placeholder="Africa/Kigali" onChange={event => changeSchedule({ timezone: event.target.value })} /></label></div>
        <label><input type="checkbox" checked={editableSchedule.enabled} onChange={event => changeSchedule({ enabled: event.target.checked })} /> Enable scheduled cycle</label>
        <fieldset><legend>Run on</legend><div className="actions">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input type="checkbox" checked={editableSchedule.weekdays.includes(index)} onChange={event => changeSchedule({ weekdays: event.target.checked ? [...new Set([...editableSchedule.weekdays, index])].sort() : editableSchedule.weekdays.filter(item => item !== index) })} /> {day}</label>)}</div></fieldset>
        <button className="btn" disabled={saveSchedule.isPending || (editableSchedule.enabled && editableSchedule.weekdays.length === 0)} onClick={() => saveSchedule.mutate()}>{saveSchedule.isPending ? "Saving…" : "Save account schedule"}</button>
      </> : <p className="empty">Select an account to configure its research schedule.</p>}
      <div className="actions"><button className="btn primary" disabled={!selectedAccountId || run.isPending} onClick={() => { setMessage(""); run.mutate(); }}>{run.isPending ? "Queuing…" : "Run research now"}</button><span className="muted">Universe: {categories.join(" · ")}</span></div>
    </article>

    {message && <p className="notice">{message}</p>}
    {runs.isPending ? <p>Loading research…</p> : latest ? <>
      <article className="card">
        <div className="actions"><strong>Cycle status: <span className={latest.state === "DEGRADED" ? "bad" : "good"}>{latest.state}</span></strong><small>Updated {new Date(latest.updated_at).toLocaleString()}</small></div>
        {latest.state === "RESEARCHING" || latest.state === "QUEUED" ? <p className="muted">Provider discovery and bounded agent review are in progress…</p> : null}
        {latest.state === "DEGRADED" ? <div><h3>DEGRADED</h3><p>No recommendation was fabricated for unavailable categories: {missingCategories.join(", ") || "agent evidence incomplete"}.</p><ul>{degradedReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div> : null}
      </article>
      <div className="grid">{candidates.map(item => <article className="card" key={item.category}>
        <p className="muted">{item.category}</p><h2>{item.instrument}</h2><strong className="good">Score {item.score.toFixed(2)}</strong>
        <dl><dt>Regime</dt><dd>{item.fingerprint.regime}</dd><dt>Trend</dt><dd>{item.fingerprint.trend_score.toFixed(3)}</dd><dt>Volatility</dt><dd>{item.fingerprint.volatility_score.toFixed(3)}</dd><dt>Data quality</dt><dd>{Math.round(item.fingerprint.data_quality * 100)}%</dd><dt>Source</dt><dd>{item.fingerprint.source}</dd></dl>
        <h3>Evidence</h3><ul>{[...item.evidence, ...item.agent_evidence].map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}</ul>
        <div className="actions"><input aria-label={`Replacement for ${item.category}`} placeholder="Replacement symbol" value={replacements[item.category] ?? ""} onChange={event => setReplacements({ ...replacements, [item.category]: event.target.value })}/><button className="btn" disabled={!replacements[item.category] || decide.isPending} onClick={() => decide.mutate({ action: "REPLACE", category: item.category, instrument: replacements[item.category] })}>Replace</button></div>
      </article>)}</div>
      <div className="actions"><button className="btn primary" disabled={latest.state !== "MARKETS_PENDING_APPROVAL" || decide.isPending} onClick={() => decide.mutate({ action: "APPROVE" })}>Approve universe</button><button className="btn" disabled={!(["MARKETS_PENDING_APPROVAL", "DEGRADED"].includes(latest.state)) || decide.isPending} onClick={() => decide.mutate({ action: "NO_TRADE", reason: "Operator selected no trade" })}>No trade</button><button className="btn" disabled={decide.isPending} onClick={() => decide.mutate({ action: "RERUN" })}>Rerun</button></div>
    </> : <p className="empty">No persisted research run yet. The scheduler will run automatically, or you can run it now.</p>}

    <article className="card"><h2>Recorded selections</h2>{selections.data?.length ? <ul className="record-list">{selections.data.map(item => <li key={item.id}><strong>{String(item.action)}</strong><span>{Object.entries((item.selected as Record<string, string>) ?? {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "No trade"}</span><small>{new Date(item.created_at).toLocaleString()}</small></li>)}</ul> : <p className="empty">No HIL-1 decisions yet.</p>}</article>
    <article className="card"><h2>Market research archive</h2><p className="muted">Every completed cycle is saved in an immutable timestamped folder.</p>{artifacts.data?.length ? <ul className="record-list">{artifacts.data.map(item => <li key={item.run_id}><strong>{item.state}</strong><span>{item.relative_path}</span><small>{new Date(item.completed_at).toLocaleString()} · SHA-256 {item.checksum.slice(0, 12)}…</small></li>)}</ul> : <p className="empty">No archived market-research cycles yet.</p>}</article>
  </section>;
}
