"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ProgressiveList, newestFirst } from "@/components/ProgressiveList";
import { api, type Resource } from "@/lib/api";

type Experiment = Resource & { instrument: string; engine: string; status: string; combination_count: number; outer_holdout_used: boolean };
type GridRow = { hypothesis_id: string; family: string; direction: string; window: number; atr_stop: string; reward_r: string; robust_region: boolean; selected?: boolean; inner_validation: { trade_count: number; net_pnl: number } };

export function ResearchDataPanel({ accountId }: { accountId: string }) {
  const client = useQueryClient();
  const [instrument, setInstrument] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [timeframe, setTimeframe] = useState("1h");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [message, setMessage] = useState("");
  const [selectedExperiment, setSelectedExperiment] = useState("");
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const datasets = useQuery<Resource[]>({ queryKey: ["research-data", "datasets", accountId], queryFn: () => api(`/research-data/datasets?account_id=${accountId}`), enabled: Boolean(accountId), refetchInterval: 20000 });
  const imports = useQuery<Resource[]>({ queryKey: ["research-data", "imports", accountId], queryFn: () => api(`/research-data/imports?account_id=${accountId}`), enabled: Boolean(accountId), refetchInterval: 10000 });
  const experiments = useQuery<Experiment[]>({ queryKey: ["research-data", "experiments", accountId], queryFn: () => api(`/research-data/experiments?account_id=${accountId}`), enabled: Boolean(accountId), refetchInterval: 20000 });
  const results = useQuery<{ experiments: GridRow[] }>({
    queryKey: ["research-data", "experiment", selectedExperiment, accountId],
    queryFn: async () => {
      const data = await api<{ experiments?: GridRow[] }>(`/research-data/experiments/${selectedExperiment}/results`);
      return { ...data, experiments: data.experiments ?? [] };
    },
    enabled: Boolean(selectedExperiment) && Boolean(experiments.data?.some(item => item.id === selectedExperiment)),
  });
  const ingest = useMutation({
    mutationFn: () => api("/research-data/imports", { method: "POST", body: JSON.stringify({ account_id: accountId, connection_id: connectionId, instrument, timeframe, start_at: new Date(startAt).toISOString(), end_at: new Date(endAt).toISOString() }) }),
    onSuccess: async () => { setMessage("History import queued. This builds research data and features, not executable orders."); await client.invalidateQueries({ queryKey: ["research-data", "imports", accountId] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const sources = (connections.data ?? []).filter(item => item.state !== "DELETED" && ["DUKASCOPY", "CCXT", "YAHOO_FINANCE"].includes(String(item.provider)));
  const currentExperiment = experiments.data?.find(item => item.id === selectedExperiment);
  return <article className="card form-stack">
    <h2>Historical data & quantitative research</h2>
    <p>Independent datasets and TA-Lib features support research. MT5 retains broker authority. Vectorbt searches discovery data; formal validation and Nautilus order replay must pass before forward paper testing.</p>
    {!accountId ? <p>Select an account to inspect its research data.</p> : <>
      {datasets.isError || imports.isError || experiments.isError ? <p role="alert">Research data could not be loaded. Check API connectivity.</p> : null}
      <p>{datasets.data?.length ?? 0} archived datasets · {experiments.data?.length ?? 0} quantitative experiments</p>
      <details><summary>Import independent history</summary><form className="form-stack" onSubmit={event => { event.preventDefault(); ingest.mutate(); }}>
        <label>Public research connection<select required value={connectionId} onChange={event => setConnectionId(event.target.value)}><option value="">Select a verified account-bound source</option>{sources.map(item => <option key={item.id} value={item.id}>{String(item.name)} · {String(item.provider)}</option>)}</select></label>
        <label>Mapped broker instrument<input required value={instrument} onChange={event => setInstrument(event.target.value)} /></label>
        <div className="form-grid"><label>Timeframe<select value={timeframe} onChange={event => setTimeframe(event.target.value)}>{["1m", "5m", "15m", "1h", "4h", "1d"].map(value => <option key={value}>{value}</option>)}</select></label><label>Start (local time)<input required type="datetime-local" value={startAt} onChange={event => setStartAt(event.target.value)} /></label><label>End (local time)<input required type="datetime-local" value={endAt} onChange={event => setEndAt(event.target.value)} /></label></div>
        <p className="muted">Up to 31 days per job and four concurrent imports. Sources require explicit symbol mappings and a verified HISTORY or REFERENCE binding. Imports never grant execution permission.</p>
        <button className="btn primary" disabled={ingest.isPending || !connectionId}>Queue history import</button>
      </form></details>
      {message ? <p className={`notice ${ingest.isError ? "bad" : "good"}`}>{message}</p> : null}
      {imports.data?.length ? <ProgressiveList items={newestFirst(imports.data)} label="history imports" scopeKey={accountId}>{visible => <ul className="record-list">{visible.map(item => <li key={item.id}><strong>{String(item.instrument)} · {item.state}</strong><small>{String(item.timeframe)} · {String(item.start_at)} → {String(item.end_at)}{item.error_type ? ` · ${String(item.error_type)}` : ""}</small></li>)}</ul>}</ProgressiveList> : null}
      {experiments.data?.length ? <><label>Quantitative experiment<select value={currentExperiment?.id ?? ""} onChange={event => setSelectedExperiment(event.target.value)}><option value="">Choose an experiment to inspect its parameter grid</option>{experiments.data.map(item => <option key={item.id} value={item.id}>{item.instrument} · {item.status} · {item.combination_count} combinations</option>)}</select></label>{currentExperiment ? <p>{currentExperiment.engine} · Outer holdout used for optimization: {currentExperiment.outer_holdout_used ? "YES — review required" : "No"}</p> : null}</> : <p className="empty">Selected-pair research automatically records discovery-only quantitative experiments here.</p>}
      {currentExperiment && results.isError ? <p role="alert">Unable to load the archived parameter grid.</p> : null}
      {currentExperiment && results.data ? <ProgressiveList items={results.data.experiments} label="parameter rows" scopeKey={`${accountId}:${selectedExperiment}`} pageSize={12}>{visible => <div className="table-wrap"><table><thead><tr><th>Family</th><th>Direction</th><th>Window</th><th>ATR stop</th><th>Reward R</th><th>Inner-validation trades</th><th>Net PnL</th><th>Stable region</th></tr></thead><tbody>{visible.map((row, index) => <tr key={`${row.hypothesis_id}-${index}`}><td>{row.family}</td><td>{row.direction}</td><td>{row.window}</td><td>{row.atr_stop}</td><td>{row.reward_r}</td><td>{row.inner_validation.trade_count}</td><td>{row.inner_validation.net_pnl.toFixed(4)}</td><td>{row.selected ? "Selected for held-out screening" : row.robust_region ? "Supported" : "Not eligible"}</td></tr>)}</tbody></table><p className="muted">Unit-size fast-research PnL, not account profit. No multiple-testing significance or execution approval is implied.</p></div>}</ProgressiveList> : null}
    </>}
  </article>;
}
