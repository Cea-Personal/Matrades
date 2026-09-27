"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";
import { TradeSetupSummary, type StrategyTradeSetup } from "./TopPairStrategies";

export function StrategyMonitoring({ version }: { version?: Resource }) {
  const client = useQueryClient();
  const [days, setDays] = useState(30);
  const [message, setMessage] = useState("");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const paper = useQuery<Resource[]>({ queryKey: ["strategies", "paper-trading"], queryFn: () => api("/strategies/paper-trading"), refetchInterval: 5000 });
  const monitors = useQuery<Resource[]>({ queryKey: ["strategies", "monitoring"], queryFn: () => api("/strategies/monitoring"), refetchInterval: 5000 });
  const current = paper.data?.find(item => item.strategy_version_id === version?.id && item.state === "RUNNING");
  const evidence = version?.validation_evidence as Record<string, boolean> | undefined;
  const robustnessPassed = ["parameter_sensitivity", "cost_stress"].every(key => evidence?.[key] !== false);
  const canStart = version?.state === "VALIDATING" && robustnessPassed && ["backtest", "out_of_sample", "walk_forward", "stress", "policy"].every(key => evidence?.[key]);
  const health = monitors.data?.find(item => item.id === version?.id)?.strategy_health as { suspend?: boolean } | undefined;
  const canActivate = ["APPROVED", "SUSPENDED"].includes(version?.state ?? "") && evidence?.paper_forward && robustnessPassed && !health?.suspend;
  const signal = monitors.data?.find(item => item.id === version?.id)?.latest_signal as StrategyTradeSetup | undefined;
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["strategies"] }); };
  const action = useMutation({
    mutationFn: async ({ path, body, notice }: { path: string; body?: unknown; notice: string }) => {
      await api(path, { method: "POST", body: JSON.stringify(body ?? {}) });
      return notice;
    },
    onSuccess: async notice => { setMessage(notice); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const hasOpen = Boolean((current?.open_positions as unknown[] | undefined)?.length || (current?.pending_entries as unknown[] | undefined)?.length);
  const entriesStopped = Boolean(current?.entry_cutoff && Date.parse(String(current.entry_cutoff)) <= now);
  return <section className="section-stack">
    <article className="card form-stack">
      <h2>Forward paper trading</h2>
      <p>After formal validation, the selected version monitors incoming completed candles. Simulated fills, costs and outcomes are recorded automatically. History before the session is used only to initialize indicators.</p>
      <p className="muted">Selected version: {String((version?.specification as { name?: string } | undefined)?.name ?? "Create a strategy version first")} · {version?.state ?? "—"}</p>
      <label>Observation duration (days)<input type="number" min={1} max={90} value={days} onChange={event => setDays(Number(event.target.value))} /></label>
      <div className="actions">
        <button className="btn" disabled={!canStart || Boolean(current) || action.isPending || !Number.isInteger(days) || days < 1 || days > 90} onClick={() => action.mutate({ path: `/strategies/${version!.id}/paper-trading`, body: { duration_days: days }, notice: "Forward paper session started. The monitor records decisions and simulated trades automatically." })}>Start paper session</button>
        <button className="btn" disabled={!current || entriesStopped || action.isPending} onClick={() => action.mutate({ path: `/strategies/${version!.id}/paper-trading/${current!.id}/stop-entries`, notice: "New paper entries stopped. Existing simulated positions remain monitored until they exit." })}>Stop new paper entries</button>
        <button className="btn" disabled={!current || !entriesStopped || hasOpen || action.isPending} onClick={() => action.mutate({ path: `/strategies/${version!.id}/paper-trading/${current!.id}/complete`, notice: "Paper evidence reviewed. A failed review remains available as evidence and the strategy can start a clean new session." })}>Finish and review paper results</button>
      </div>
      <p className="muted">Approval requires at least 10 completed paper trades, passing performance and loss limits, complete observations, and no pending entries or open simulated positions.</p>
      {paper.isError ? <p role="alert">Unable to load paper sessions: {paper.error.message}</p> : null}
      {(paper.data ?? []).filter(item => item.strategy_version_id === version?.id).map(item => <div className="inset form-stack" key={item.id}>
        <strong>Paper session · {item.state}</strong>
        <p>Trades: {String(item.trade_count ?? 0)} · Simulated P&amp;L: {String(item.net_profit ?? "—")} · Drawdown: {String(item.max_drawdown ?? "—")}</p>
        {item.gates ? <p className="muted">{Object.entries(item.gates as Record<string, boolean>).map(([gate, passed]) => `${gate.replaceAll("_", " ")}: ${passed ? "PASS" : "FAIL"}`).join(" · ")}</p> : null}
        <small>Results use the strategy’s risk assumption in a simulated account. Broker lot sizing is checked separately for live Trade Plans.</small>
        <small>Last observation: {item.last_checked_at ? new Date(String(item.last_checked_at)).toLocaleString() : "Waiting for first observation"}</small>
        {item.failure ? <p role="alert">{String(item.failure)}</p> : null}
        {item.latest_signal ? <TradeSetupSummary setup={item.latest_signal as StrategyTradeSetup} /> : null}
        <details><summary>Recorded simulated trades ({String(item.trade_count ?? 0)})</summary><ul>{((item.trades as { entered_at: string; exited_at: string; entry: string; simulation_account_pnl: string }[] | undefined) ?? []).map(trade => <li key={trade.entered_at}>{new Date(trade.entered_at).toLocaleString()} → {new Date(trade.exited_at).toLocaleString()} · Entry {trade.entry} · P&amp;L {trade.simulation_account_pnl}</li>)}</ul></details>
      </div>)}
    </article>
    <article className="card form-stack">
      <h2>Active strategy monitoring</h2>
      <p>Activate a paper-validated version to evaluate current market data. A fresh eligible signal can produce a Trade Plan through the existing broker and risk checks.</p>
      <div className="actions">
        <button className="btn primary" disabled={!canActivate || action.isPending} onClick={() => action.mutate({ path: `/strategies/promote/${version!.id}`, notice: "Strategy monitoring activated. Current decisions appear below as fresh candles arrive." })}>Activate strategy</button>
        <button className="btn" disabled={version?.state !== "ACTIVE" || action.isPending} onClick={() => action.mutate({ path: `/strategies/${version!.id}/transitions`, body: { target: "SUSPENDED" }, notice: "Strategy monitoring suspended." })}>Suspend strategy</button>
        <button className="btn" disabled={version?.state !== "ACTIVE" || signal?.status !== "SIGNAL" || !signal.expires_at || Date.parse(signal.expires_at) <= now || action.isPending} onClick={() => action.mutate({ path: `/strategies/${version!.id}/trade-plans`, notice: "Trade Plan created using the active strategy signal and current risk checks." })}>Create Trade Plan</button>
      </div>
      {monitors.isError ? <p role="alert">Unable to load monitoring: {monitors.error.message}</p> : null}
      {(monitors.data ?? []).filter(item => item.state !== "PAPER_TRADING").map(item => <div className="inset" key={item.id}>
        <h3>{String(item.instrument)} · {String(item.name)} · {item.state}</h3>
        {item.state === "ACTIVE" && item.latest_signal ? <TradeSetupSummary setup={item.latest_signal as StrategyTradeSetup} /> : <p>{item.state === "APPROVED" ? "Validated and ready to activate." : item.state === "SUSPENDED" ? "Monitoring is suspended." : "Waiting for first evaluation."}</p>}
      </div>)}
    </article>
    {message ? <p className="notice" role="status">{message}</p> : null}
  </section>;
}
