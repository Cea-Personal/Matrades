"use client";

import { useState } from "react";
import Link from "next/link";
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
  configured: boolean;
  saved_at: string | null;
};
type ResearchArtifact = { run_id: string; account_id: string; cycle_type: string; state: string; completed_at: string; relative_path: string; checksum: string };
type MatrixLane = { asset_class: string; instrument_type: string; enabled: boolean };
type Matrix = { id?: string; account_id: string; version: number; lanes: MatrixLane[] };
type TypedLaneResult = {
  lane: { asset_class: string; instrument_type: string };
  status: string;
  reason_code?: string;
  candidate?: { listing: { symbol: string; venue: string }; score: number; evidence: string[] };
};

export function MarketSelection() {
  const queryClient = useQueryClient();
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const [accountId, setAccountId] = useState("");
  const [scheduleDraft, setScheduleDraft] = useState<AccountSchedule | null>(null);
  const [scheduleEditing, setScheduleEditing] = useState(false);
  const [message, setMessage] = useState("");
  const selectedAccountId = accountId || accounts.data?.[0]?.id || "";
  const selectedAccountName = String(accounts.data?.find(item => item.id === selectedAccountId)?.name ?? "No account selected");
  const artifacts = useQuery<ResearchArtifact[]>({
    queryKey: ["research", "artifacts", selectedAccountId],
    queryFn: () => api(`/research/artifacts?account_id=${selectedAccountId}`),
    enabled: Boolean(selectedAccountId),
  });
  const matrix = useQuery<Matrix>({ queryKey: ["research", "matrix", selectedAccountId], queryFn: () => api(`/accounts/${selectedAccountId}/research-matrix`), enabled: Boolean(selectedAccountId) });
  const typedRuns = useQuery<Resource[]>({ queryKey: ["research", "typed-runs", selectedAccountId], queryFn: () => api(`/research-runs?account_id=${selectedAccountId}`), enabled: Boolean(selectedAccountId), refetchInterval: 10000 });
  const accountSchedule = useQuery<AccountSchedule>({
    queryKey: ["configuration", "account", selectedAccountId, "research-schedule"],
    queryFn: () => api(`/configuration/accounts/${selectedAccountId}/research-schedule`),
    enabled: Boolean(selectedAccountId),
  });
  const editableSchedule = scheduleDraft?.account_id === selectedAccountId ? scheduleDraft : accountSchedule.data;

  const typedLatest = typedRuns.data?.find(item => String(item.account_id) === selectedAccountId);
  const latest = typedLatest;
  const typedResults = (typedLatest?.lane_results as TypedLaneResult[] | undefined) ?? [];
  const candidates = (typedLatest?.ranked_candidates as Candidate[] | undefined) ?? [];
  const runTyped = useMutation({
    mutationFn: () => api<Resource>("/research-runs", { method: "POST", body: JSON.stringify({ account_id: selectedAccountId }) }),
    onSuccess: async () => { setMessage("Typed matrix cycle queued for the selected account. Every enabled lane will end in a safe terminal state."); await queryClient.invalidateQueries({ queryKey: ["research", "typed-runs", selectedAccountId] }); },
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
    onSuccess: async result => { setScheduleDraft(result); setScheduleEditing(false); setMessage("Research schedule saved for this trading account."); await queryClient.invalidateQueries({ queryKey: ["configuration", "account", selectedAccountId, "research-schedule"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const changeSchedule = (patch: Partial<AccountSchedule>) => {
    if (editableSchedule) setScheduleDraft({ ...editableSchedule, ...patch });
  };
  const removeSchedule = useMutation({
    mutationFn: () => api<AccountSchedule>(`/configuration/accounts/${selectedAccountId}/research-schedule`, { method: "DELETE" }),
    onSuccess: async result => { setScheduleDraft(result); setScheduleEditing(false); setMessage("Research schedule removed. Automatic research is disabled for this account."); await queryClient.invalidateQueries({ queryKey: ["configuration", "account", selectedAccountId, "research-schedule"] }); },
    onError: (error: Error) => setMessage(error.message),
  });

  const nextRun = editableSchedule?.next_run_at ? new Date(editableSchedule.next_run_at).toLocaleString() : "Schedule disabled";
  const enabledLanes = (matrix.data?.lanes ?? []).filter(lane => lane.enabled);
  const degradedReasons = (latest?.degraded_reasons as string[] | undefined) ?? [];
  const missingCategories = (latest?.missing_categories as string[] | undefined) ?? [];

  return <section className="section-stack">
    <header>
      <p className="eyebrow">Autonomous research</p>
      <h1>Autonomous market research</h1>
      <p className="muted">The research agents autonomously discover and rank the best candidate in every enabled asset-class × instrument-type lane.</p>
    </header>

    <article className="card form-stack">
      <div><h2>Per-account research cycle</h2><p className="muted">The scheduler checks each account every minute. Next scheduled cycle for this account: {nextRun} ({editableSchedule?.timezone ?? "UTC"})</p></div>
      <label>Trading account<select value={selectedAccountId} onChange={event => { setAccountId(event.target.value); setScheduleDraft(null); setScheduleEditing(false); }}>
        {!accounts.data?.length && <option value="">Configure an account first</option>}
        {accounts.data?.map(account => <option key={account.id} value={account.id}>{String(account.name)}</option>)}
      </select></label>
      {editableSchedule?.configured && !scheduleEditing ? <div className="inset form-stack"><strong>Saved account schedule</strong><span>{editableSchedule.enabled ? `${editableSchedule.run_at} · ${editableSchedule.timezone}` : "Disabled"}</span><small>Next run: {nextRun}{editableSchedule.saved_at ? ` · last saved ${new Date(editableSchedule.saved_at).toLocaleString()}` : ""}</small><div className="actions"><button className="btn" onClick={() => setScheduleEditing(true)}>Edit / replace schedule</button><button className="btn danger" disabled={removeSchedule.isPending} onClick={() => removeSchedule.mutate()}>{removeSchedule.isPending ? "Removing…" : "Remove schedule"}</button></div></div> : editableSchedule ? <>
        <div className="form-grid"><label>Run time<input type="time" value={editableSchedule.run_at} onChange={event => changeSchedule({ run_at: event.target.value })} /></label><label>Timezone<input value={editableSchedule.timezone} placeholder="Africa/Kigali" onChange={event => changeSchedule({ timezone: event.target.value })} /></label></div>
        <label><input type="checkbox" checked={editableSchedule.enabled} onChange={event => changeSchedule({ enabled: event.target.checked })} /> Enable scheduled cycle</label>
        <fieldset><legend>Run on</legend><div className="actions">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input type="checkbox" checked={editableSchedule.weekdays.includes(index)} onChange={event => changeSchedule({ weekdays: event.target.checked ? [...new Set([...editableSchedule.weekdays, index])].sort() : editableSchedule.weekdays.filter(item => item !== index) })} /> {day}</label>)}</div></fieldset>
        <div className="actions"><button className="btn primary" disabled={saveSchedule.isPending || (editableSchedule.enabled && editableSchedule.weekdays.length === 0)} onClick={() => saveSchedule.mutate()}>{saveSchedule.isPending ? "Saving…" : editableSchedule.configured ? "Replace account schedule" : "Save new account schedule"}</button>{editableSchedule.configured ? <button className="btn" onClick={() => { setScheduleDraft(null); setScheduleEditing(false); }}>Cancel</button> : null}</div>
      </> : <p className="empty">Select an account to configure its research schedule.</p>}
      <p className="muted">Manual runs use the enabled typed matrix below; a symbol list never determines the instrument type.</p>
    </article>

    <article className="card form-stack">
      <div><h2>Typed research matrix · account {String(accounts.data?.find(item => item.id === selectedAccountId)?.name ?? "")}</h2><p className="muted">Read-only here. Only configured lanes, latest statuses, and selected candidates are shown. Full decision evidence is archived in Extras.</p></div>
      {enabledLanes.length ? <div className="grid two">{enabledLanes.map(lane => {
        const result = typedResults.find(item => item.lane.asset_class === lane.asset_class && item.lane.instrument_type === lane.instrument_type);
        return <article className="card form-stack" key={`${lane.asset_class}:${lane.instrument_type}`}><strong>{lane.asset_class} · {lane.instrument_type}</strong><p className={result?.status === "READY" ? "good" : result?.status === "NO_TRADE" ? "warn" : "muted"}>{result?.status ?? "NOT_RUN"}</p>{result?.candidate ? <><p>{result.candidate.listing.symbol} · {result.candidate.listing.venue}</p><small>Score {result.candidate.score.toFixed(2)}</small></> : <small>{result?.reason_code?.replaceAll("_", " ") ?? "No completed lane result yet"}</small>}</article>;
      })}</div> : <p className="empty">No research candidates are enabled for this account. Configure the account research matrix first.</p>}
      <div className="actions"><button className="btn primary" disabled={!selectedAccountId || runTyped.isPending || !enabledLanes.length} onClick={() => runTyped.mutate()}>{runTyped.isPending ? "Queuing…" : "Run configured matrix now"}</button><Link className="btn" href="/extras?folder=market-research">View detailed evidence in Extras</Link><span className="muted">Matrix version {matrix.data?.version ?? 1} · {enabledLanes.length} configured candidates</span></div>
    </article>

    {message && <p className="notice">{message}</p>}
    <article className="card"><h2>Cycle outcome · {selectedAccountName}</h2><p className="muted">Only the latest cycle, candidates, terminal lane statuses, and evidence for this trading account are shown below.</p></article>
    {!selectedAccountId ? <p className="empty">Select a trading account to view its cycle information.</p> : typedRuns.isPending ? <p>Loading research…</p> : latest ? <>
      <article className="card">
        <div className="actions"><strong>Cycle status: <span className={latest.state === "DEGRADED" ? "bad" : "good"}>{latest.state}</span></strong><small>Updated {new Date(latest.updated_at).toLocaleString()}</small></div>
        {latest.state === "RESEARCHING" || latest.state === "QUEUED" ? <p className="muted">Provider discovery and bounded agent review are in progress…</p> : null}
        {latest.state === "DEGRADED" ? <div><h3>DEGRADED</h3><p>No recommendation was fabricated for unavailable categories: {missingCategories.join(", ") || "agent evidence incomplete"}.</p><ul>{degradedReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div> : null}
      </article>
      <div className="grid">{candidates.map(item => <article className="card" key={item.category}>
        <p className="muted">{item.category}</p><h2>{item.instrument}</h2><strong className="good">Score {item.score.toFixed(2)}</strong>
        <dl><dt>Regime</dt><dd>{item.fingerprint.regime}</dd><dt>Trend</dt><dd>{item.fingerprint.trend_score.toFixed(3)}</dd><dt>Volatility</dt><dd>{item.fingerprint.volatility_score.toFixed(3)}</dd><dt>Data quality</dt><dd>{Math.round(item.fingerprint.data_quality * 100)}%</dd><dt>Source</dt><dd>{item.fingerprint.source}</dd></dl>
        <h3>Evidence</h3><ul>{[...item.evidence, ...item.agent_evidence].map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}</ul>

      </article>)}</div>
      <div className="actions"><span className="muted">Candidates are selected by the scheduled research cycle and passed to strategy research automatically.</span><button className="btn" disabled={runTyped.isPending} onClick={() => runTyped.mutate()}>Run typed matrix again</button></div>
    </> : <p className="empty">No persisted research run exists for {selectedAccountName}. Its scheduler will run automatically, or you can run it now.</p>}

    <article className="card"><h2>Market research archive · {selectedAccountName}</h2><p className="muted">Only completed cycles for this trading account are listed. Every artifact has an immutable completion timestamp.</p>{!selectedAccountId ? <p className="empty">Select a trading account to view its research archive.</p> : artifacts.isPending ? <p>Loading this account&apos;s archive…</p> : artifacts.data?.length ? <ul className="record-list">{artifacts.data.map(item => <li key={item.run_id}><strong>{item.state}</strong><span>{item.relative_path}</span><small>Completed timestamp: {new Date(item.completed_at).toLocaleString()} · SHA-256 {item.checksum.slice(0, 12)}…</small></li>)}</ul> : <p className="empty">No archived market-research cycles exist for {selectedAccountName}.</p>}</article>
  </section>;
}
