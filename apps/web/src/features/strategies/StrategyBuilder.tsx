"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";
import { TradeSetupSummary, type StrategyTradeSetup } from "./TopPairStrategies";

type Origin = "AI_GENERATED" | "AI_ASSISTED";
type Artifact = { run_id: string; cycle_type: string; state: string; completed_at: string; relative_path: string; checksum: string };
type ResearchContext = { ready: boolean; reason: string | null; market_selection_id?: string; instrument?: string; category?: string; market_observed_at?: string; historical_provider?: string };

function dateInput(daysAgo: number) {
  const value = new Date(Date.now() - daysAgo * 86_400_000);
  return value.toISOString().slice(0, 10);
}

export function StrategyBuilder() {
  const queryClient = useQueryClient();
  const drafts = useQuery<Resource[]>({ queryKey: ["strategies", "drafts"], queryFn: () => api("/strategies"), refetchInterval: query => query.state.data?.some(item => ["QUEUED", "RESEARCHING"].includes(item.state)) ? 3000 : 15000 });
  const versions = useQuery<Resource[]>({ queryKey: ["strategies", "versions"], queryFn: () => api("/strategies/versions") });
  const backtests = useQuery<Resource[]>({ queryKey: ["strategies", "backtests"], queryFn: () => api("/strategies/backtests"), refetchInterval: query => query.state.data?.some(item => ["QUEUED", "RUNNING"].includes(item.state)) ? 3000 : 15000 });
  const paperRuns = useQuery<Resource[]>({ queryKey: ["strategies", "paper-trading"], queryFn: () => api("/strategies/paper-trading"), refetchInterval: 5000 });
  const artifacts = useQuery<Artifact[]>({ queryKey: ["strategies", "artifacts"], queryFn: () => api("/strategies/research-artifacts") });
  const researchContext = useQuery<ResearchContext>({ queryKey: ["strategies", "research-context"], queryFn: () => api("/strategies/research-context"), refetchInterval: 15000 });
  const transcriptSources = useQuery<Resource[]>({ queryKey: ["knowledge", "youtube", "transcripts"], queryFn: () => api("/knowledge/sources") });
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const [origin, setOrigin] = useState<Origin>("AI_GENERATED");
  const [description, setDescription] = useState("");
  const [knowledgeSourceId, setKnowledgeSourceId] = useState("");
  const [paper, setPaper] = useState({ start_at: dateInput(30), end_at: dateInput(0), trade_count: "10", net_profit: "1", profit_factor: "1", max_drawdown: "0", policy_passed: true });
  const [paperRunId, setPaperRunId] = useState("");
  const [message, setMessage] = useState("");
  const marketConnections = useMemo(() => (connections.data ?? []).filter(item => ["TWELVE_DATA", "COINBASE"].includes(String(item.provider)) && item.state === "ACTIVE"), [connections.data]);
  const youtubeSources = useMemo(() => (transcriptSources.data ?? []).filter(item => item.state === "ACTIVE" && item.source_kind === "YOUTUBE_TRANSCRIPT"), [transcriptSources.data]);
  const [backtest, setBacktest] = useState({ strategy_version_id: "", connection_id: "", instrument: "EUR/USD", start_at: dateInput(7), end_at: dateInput(0), timeframe: "1h", initial_equity: "10000", spread: "0.0001", commission: "0", slippage: "0.00005", max_daily_loss: "500", max_total_loss: "1000" });
  const selectedVersionId = backtest.strategy_version_id || versions.data?.[0]?.id || "";
  const selectedConnectionId = backtest.connection_id || marketConnections[0]?.id || "";
  const activePaperRunId = paperRunId || paperRuns.data?.find(item => item.strategy_version_id === selectedVersionId && ["QUEUED", "RUNNING"].includes(item.state))?.id || "";
  const refresh = async () => { await queryClient.invalidateQueries({ queryKey: ["strategies"] }); };

  const create = useMutation({
    mutationFn: () => api<Resource>("/strategies/drafts", { method: "POST", body: JSON.stringify({ origin, description: description || null, knowledge_source_id: knowledgeSourceId || null }) }),
    onSuccess: async () => { setDescription(""); setKnowledgeSourceId(""); setMessage("Strategy research queued. Transcript evidence will be converted into cited hypotheses and deterministic rules before any backtest gate."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const submit = useMutation({
    mutationFn: (id: string) => api<Resource>(`/strategies/submit/${id}`, { method: "POST" }),
    onSuccess: async () => { setMessage("Canonical strategy version created after duplicate screening."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const runBacktest = useMutation({
    mutationFn: () => api<Resource>(`/strategies/${selectedVersionId}/backtests`, { method: "POST", body: JSON.stringify({ ...backtest, connection_id: selectedConnectionId, start_at: new Date(`${backtest.start_at}T00:00:00Z`).toISOString(), end_at: new Date(`${backtest.end_at}T23:59:59Z`).toISOString(), initial_equity: Number(backtest.initial_equity), spread: Number(backtest.spread), commission: Number(backtest.commission), slippage: Number(backtest.slippage), max_daily_loss: Number(backtest.max_daily_loss), max_total_loss: Number(backtest.max_total_loss) }) }),
    onSuccess: async () => { setMessage("Provider-backed point-in-time backtest queued."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const startPaper = useMutation({
    mutationFn: () => api<Resource>(`/strategies/${selectedVersionId}/paper-trading`, { method: "POST", body: JSON.stringify({ observation_start: new Date(`${paper.start_at}T00:00:00Z`).toISOString(), observation_end: new Date(`${paper.end_at}T23:59:59Z`).toISOString(), notes: "Paper evidence is recorded separately from backtest evidence." }) }),
    onSuccess: async (result) => { setPaperRunId(result.id); setMessage("Paper-trading gate opened. Record observed paper outcomes before a Trade Plan can be created."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const completePaper = useMutation({
    mutationFn: async () => { if (!activePaperRunId) throw new Error("Start paper trading first"); return api(`/strategies/${selectedVersionId}/paper-trading/${activePaperRunId}/complete`, { method: "POST", body: JSON.stringify({ trade_count: Number(paper.trade_count), net_profit: Number(paper.net_profit), profit_factor: Number(paper.profit_factor), max_drawdown: Number(paper.max_drawdown), policy_passed: paper.policy_passed, source: "paper-observation" }) }); },
    onSuccess: async () => { setMessage("Paper evidence recorded. A passing paper gate moves the strategy to APPROVED."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const createTradePlan = useMutation({
    mutationFn: () => api<Resource>(`/strategies/${selectedVersionId}/trade-plans`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: async () => { setMessage("Risk-validated Trade Plan created. It remains non-authorized until execution revalidation succeeds."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const submitGeneration = (event: FormEvent) => { event.preventDefault(); setMessage(""); create.mutate(); };
  const submitBacktest = (event: FormEvent) => { event.preventDefault(); setMessage(""); runBacktest.mutate(); };

  return <section className="section-stack">
    <header><p className="eyebrow">AI strategy lifecycle</p><h1>Strategy research & validation</h1><p className="muted">AI researches, deterministic services compile and validate, and only passing versions are promoted for autonomous execution.</p></header>
    <article className="card form-stack"><h2>Research basis</h2><p className="muted">Strategy research is pinned to the latest autonomous market cycle, its approved market selection, and provider history; you do not choose another pair here.</p>{researchContext.isPending ? <p>Checking market research evidence…</p> : researchContext.data?.ready ? <dl><dt>Selected instrument</dt><dd>{researchContext.data.instrument} · {researchContext.data.category}</dd><dt>Market evidence observed</dt><dd>{researchContext.data.market_observed_at ? new Date(researchContext.data.market_observed_at).toLocaleString() : "—"}</dd><dt>Historical provider</dt><dd>{researchContext.data.historical_provider}</dd></dl> : <p className="notice">Not ready: {researchContext.data?.reason ?? "research context unavailable"}. Run the autonomous market cycle and configure its historical provider.</p>}</article>
    <form className="card form-stack" onSubmit={submitGeneration}><h2>Generate strategy</h2><div className="form-grid"><label>Creation mode<select value={origin} onChange={event => setOrigin(event.target.value as Origin)}><option value="AI_GENERATED">AI Generated</option><option value="AI_ASSISTED">AI Assisted</option></select></label>{origin === "AI_ASSISTED" ? <label>Your strategy idea<textarea required rows={5} placeholder="Describe the behavior, timing, and risk preferences; the selected instrument remains fixed…" value={description} onChange={event => setDescription(event.target.value)} /></label> : <label>Optional strategy focus<textarea rows={5} placeholder="For example: conservative intraday momentum with tight invalidation" value={description} onChange={event => setDescription(event.target.value)} /></label>}<label>YouTube transcript evidence<select value={knowledgeSourceId} onChange={event => setKnowledgeSourceId(event.target.value)}><option value="">Use retrieved trading knowledge</option>{youtubeSources.map(item => <option value={item.id} key={item.id}>{String(item.name ?? item.id)}</option>)}</select></label></div><p className="muted">The pipeline is transcript → hypothesis → structured rules → preliminary backtest → formal validation → paper trading → approved Trade Plan. Transcript text is evidence only; it cannot place or approve a trade.</p><button className="btn primary" disabled={create.isPending || !researchContext.data?.ready}>{create.isPending ? "Queuing…" : "Generate strategy"}</button></form>
    {message && <p className="notice">{message}</p>}
    {drafts.data?.some(item => item.trade_setup) ? <section className="section-stack">
      <h2>Strategy trade setups</h2>
      <div className="grid">{drafts.data.filter(item => item.trade_setup).map(item => <article className="card" key={item.id}>
        <h3>{String((item.research_basis as { instrument?: string } | undefined)?.instrument ?? "Trade setup")}</h3>
        <TradeSetupSummary setup={item.trade_setup as StrategyTradeSetup} />
      </article>)}</div>
    </section> : null}

    <section className="section-stack"><h2>Strategy proposals</h2><p className="muted">Review the family, rules, evidence, and breakdown. You may Accept, Edit after approval, or Reject; Similarity screening runs before a permanent version is created. The preliminary unseen holdout screen is evidence only and never replaces formal validation.</p>{drafts.isPending ? <p>Loading strategy research…</p> : drafts.data?.length ? <div className="grid">{drafts.data.map(item => {
      const proposed = (item.proposed_specification as Record<string, unknown> | null) ?? (item.specification as Record<string, unknown> | null);
      const breakdown = (item.breakdown as string[] | undefined) ?? [];
      const pack = item.evidence_pack as Record<string, unknown> | undefined;
      const fingerprint = pack?.market_fingerprint as Record<string, unknown> | undefined;
      const discovery = pack?.historical_discovery as Record<string, unknown> | undefined;
      const screen = item.preliminary_screen as { selected_hypothesis_id?: string; results?: { hypothesis_id: string; eligible: boolean; score: string; trade_count: number; reasons: string[] }[] } | undefined;
      const evidence = (item.evidence as string[] | undefined) ?? [];
      const pipeline = item.strategy_pipeline as { stages?: Record<string, string> } | undefined;
      return <article className="card form-stack" key={item.id}><div><p className="muted">{String(item.origin).replaceAll("_", " ")}</p><h3>{String(proposed?.name ?? "Research in progress")}</h3><span className={`status ${item.state.toLowerCase()}`}>{item.state}</span></div>{proposed ? <dl><dt>Strategy family</dt><dd>{String(proposed.family)}</dd><dt>Horizon</dt><dd>{String(proposed.horizon)}</dd><dt>Instruments</dt><dd>{(proposed.instruments as string[]).join(", ")}</dd><dt>Risk per trade</dt><dd>{String(proposed.risk_per_trade)}%</dd></dl> : <p className="muted">The Strategy Researcher is preparing grounded hypotheses.</p>}{pipeline?.stages ? <><h4>Conversion pipeline</h4><p className="muted">{Object.entries(pipeline.stages).map(([stage, state]) => `${stage.replaceAll("_", " ")}: ${state}`).join(" · ")}</p></> : null}{pack ? <><h4>Research basis</h4><dl><dt>Market fingerprint</dt><dd>{String(pack.instrument)} · {String(fingerprint?.regime)} · {String(fingerprint?.source)}</dd><dt>Discovery history</dt><dd>{String(discovery?.timeframe)} · checksum {String(discovery?.checksum).slice(0, 12)}…</dd><dt>Selected hypothesis</dt><dd>{screen?.selected_hypothesis_id ?? "Pending deterministic holdout screen"}</dd></dl>{evidence.length ? <p className="muted">Evidence references: {evidence.join(" · ")}</p> : null}{screen?.results?.length ? <><h4>Preliminary alternatives</h4><ul>{screen.results.map(result => <li key={result.hypothesis_id}>{result.hypothesis_id}: score {result.score} · {result.trade_count} holdout trades · {result.eligible ? "eligible" : result.reasons.join(", ")}</li>)}</ul></> : null}</> : null}{breakdown.length ? <><h4>Step-by-step breakdown</h4><ol>{breakdown.map(step => <li key={step}>{step}</li>)}</ol></> : null}<div className="actions">{item.state === "AWAITING_STRATEGY_APPROVAL" ? <span className="muted">Awaiting automated validation gates</span> : null}{item.state === "DRAFT" ? <button className="btn primary" disabled={submit.isPending} onClick={() => submit.mutate(item.id)}>Approve strategy</button> : null}</div></article>;
    })}</div> : <p className="empty">No strategy research runs yet.</p>}</section>

    <form className="card form-stack" onSubmit={submitBacktest}><h2>Run backtest</h2><p className="muted">Historical candles are fetched from a configured authoritative source. Matrades applies next-bar execution, configured spread, commission and slippage, then runs out-of-sample, walk-forward, stress, and policy validation.</p><div className="form-grid"><label>Strategy version<select required value={selectedVersionId} onChange={event => setBacktest({ ...backtest, strategy_version_id: event.target.value })}><option value="">Create and submit a strategy first</option>{versions.data?.map(item => <option value={item.id} key={item.id}>{String((item.specification as Record<string, unknown>)?.name ?? item.id)}</option>)}</select></label><label>Historical data source<select required value={selectedConnectionId} onChange={event => setBacktest({ ...backtest, connection_id: event.target.value })}><option value="">Configure Twelve Data or Coinbase</option>{marketConnections.map(item => <option value={item.id} key={item.id}>{String(item.name)} · {String(item.provider)}</option>)}</select></label><label>Instrument<input required value={backtest.instrument} onChange={event => setBacktest({ ...backtest, instrument: event.target.value.toUpperCase() })} /></label><label>Timeframe<select value={backtest.timeframe} onChange={event => setBacktest({ ...backtest, timeframe: event.target.value })}><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select></label><label>Start date<input type="date" required value={backtest.start_at} onChange={event => setBacktest({ ...backtest, start_at: event.target.value })} /></label><label>End date<input type="date" required value={backtest.end_at} onChange={event => setBacktest({ ...backtest, end_at: event.target.value })} /></label><label>Initial equity<input type="number" min="1" value={backtest.initial_equity} onChange={event => setBacktest({ ...backtest, initial_equity: event.target.value })} /></label><label>Spread cost<input type="number" min="0" step="any" value={backtest.spread} onChange={event => setBacktest({ ...backtest, spread: event.target.value })} /></label><label>Commission<input type="number" min="0" step="any" value={backtest.commission} onChange={event => setBacktest({ ...backtest, commission: event.target.value })} /></label><label>Slippage<input type="number" min="0" step="any" value={backtest.slippage} onChange={event => setBacktest({ ...backtest, slippage: event.target.value })} /></label></div><button className="btn primary" disabled={!selectedVersionId || !selectedConnectionId || runBacktest.isPending}>{runBacktest.isPending ? "Queuing…" : "Run backtest"}</button></form>
    <article className="card form-stack"><h2>Paper trading → approved Trade Plan</h2><p className="muted">Paper results must be observed and recorded separately. A passing paper gate enables a risk-validated Trade Plan; it does not authorize broker execution.</p><div className="form-grid"><label>Observation start<input type="date" value={paper.start_at} onChange={event => setPaper({ ...paper, start_at: event.target.value })} /></label><label>Observation end<input type="date" value={paper.end_at} onChange={event => setPaper({ ...paper, end_at: event.target.value })} /></label><label>Paper trades<input type="number" min="0" value={paper.trade_count} onChange={event => setPaper({ ...paper, trade_count: event.target.value })} /></label><label>Net profit<input type="number" step="any" value={paper.net_profit} onChange={event => setPaper({ ...paper, net_profit: event.target.value })} /></label><label>Profit factor<input type="number" min="0" step="any" value={paper.profit_factor} onChange={event => setPaper({ ...paper, profit_factor: event.target.value })} /></label><label>Max drawdown<input type="number" min="0" step="any" value={paper.max_drawdown} onChange={event => setPaper({ ...paper, max_drawdown: event.target.value })} /></label></div><label><input type="checkbox" checked={paper.policy_passed} onChange={event => setPaper({ ...paper, policy_passed: event.target.checked })} /> Paper policy remained within limits</label><div className="actions"><button type="button" className="btn" disabled={!selectedVersionId || startPaper.isPending} onClick={() => startPaper.mutate()}>Start paper session</button><button type="button" className="btn" disabled={!selectedVersionId || completePaper.isPending} onClick={() => completePaper.mutate()}>Record paper evidence</button><button type="button" className="btn primary" disabled={!selectedVersionId || createTradePlan.isPending} onClick={() => createTradePlan.mutate()}>Create approved Trade Plan</button></div></article>

    <article className="card"><h2>Backtest & validation runs</h2>{backtests.data?.length ? <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>State</th><th>Candles</th><th>Trades</th><th>Net P&amp;L</th><th>Validation gates</th><th>Updated</th></tr></thead><tbody>{backtests.data.map(item => <tr key={item.id}><td>{String(item.instrument)}</td><td><span className={`status ${item.state.toLowerCase()}`}>{item.state}</span></td><td>{String(item.candle_count ?? "—")}</td><td>{String(item.trade_count ?? "—")}</td><td>{String((item.metrics as Record<string, string> | undefined)?.net_profit ?? "—")}</td><td>{Object.entries((item.gates as Record<string, boolean> | undefined) ?? {}).map(([gate, passed]) => `${gate}: ${passed ? "PASS" : "FAIL"}`).join(" · ") || "Pending"}</td><td>{new Date(item.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div> : <p className="empty">No provider-backed backtests yet.</p>}</article>

    <article className="card"><h2>Research archive</h2><p className="muted">Every strategy research and backtest cycle is stored in a timestamped immutable folder with a SHA-256 manifest.</p>{artifacts.data?.length ? <ul className="record-list">{artifacts.data.map(item => <li key={item.run_id}><strong>{item.cycle_type.replaceAll("_", " ")}</strong><span>{item.relative_path}</span><small>{item.completed_at ? new Date(item.completed_at).toLocaleString() : item.state} · {item.checksum.slice(0, 12)}…</small></li>)}</ul> : <p className="empty">No archived strategy cycles yet.</p>}</article>
  </section>;
}
