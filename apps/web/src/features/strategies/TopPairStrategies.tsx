"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

export type StrategyTradeSetup = {
  status: string;
  reason?: string;
  direction?: string;
  entry?: string | null;
  stop_loss?: string | null;
  take_profits?: { price: string; reward_risk: string; fraction: string }[];
  expires_at?: string;
  observed_at?: string;
  risk_per_trade_percent?: string;
  pending_checks?: string[];
};
type PipelineLink = { instrument?: string; state: string; reason?: string };

export function TradeSetupSummary({ setup }: { setup: StrategyTradeSetup }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const expired = Boolean(setup.expires_at && Date.parse(setup.expires_at) <= now);
  return <div className="inset form-stack">
    <h4>Trade setup · {expired ? "STALE" : setup.status}</h4>
    <p>{expired ? "Waiting for the strategy monitor to receive fresh market data." : setup.reason}</p>
    {setup.entry && !expired ? <>
      <dl>
        <dt>Direction</dt><dd>{setup.direction}</dd>
        <dt>Indicative entry</dt><dd>{setup.entry}</dd>
        <dt>Stop loss</dt><dd>{setup.stop_loss}</dd>
        <dt>Research simulation risk assumption</dt><dd>{setup.risk_per_trade_percent}%</dd>
        {setup.take_profits?.map((target, index) => <div key={index}>
          <dt>Take profit {index + 1}</dt>
          <dd>{target.price} · {Number(target.reward_risk).toFixed(2)}R · {(Number(target.fraction) * 100).toFixed(1)}%</dd>
        </div>)}
      </dl>
      <p className="muted">Entry uses the next bar open after the signal. These indicative levels use the latest closed candle; protection is recalculated at the actual fill. The simulation risk assumption is not approved trade sizing.</p>
    </> : null}
    {setup.pending_checks?.length ? <p className="muted">Before entry: {setup.pending_checks.join(" · ")}</p> : null}
    {setup.observed_at ? <small>Price evidence: {new Date(setup.observed_at).toLocaleString()} · Valid until {setup.expires_at ? new Date(setup.expires_at).toLocaleString() : "—"}</small> : null}
  </div>;
}

export function TopPairStrategies({ runId, links }: { runId: string; links: PipelineLink[] }) {
  const drafts = useQuery<Resource[]>({
    queryKey: ["strategies", "top-pairs", runId],
    queryFn: () => api(`/strategies?market_research_run_id=${runId}`),
    refetchInterval: 5000,
  });
  return <article className="card form-stack">
    <h2>Top-pair strategy research</h2>
    <p className="muted">Each selected pair is researched automatically. Three strategies are compared on withheld history, including stops, profit targets and trading costs.</p>
    {links.filter(item => item.state === "BLOCKED").map((item, index) => <p className="notice" key={index}>{item.instrument}: {item.reason}</p>)}
    {drafts.isError ? <p className="notice">Unable to load strategy research: {drafts.error.message}</p> : null}
    {drafts.data?.length ? <div className="grid">{drafts.data.map(item => {
      const basis = item.research_basis as { instrument?: string; market_observed_at?: string; historical_provider?: string } | undefined;
      const spec = item.proposed_specification as { name?: string } | undefined;
      return <section className="card form-stack" key={item.id}>
        <h3>{basis?.instrument} · {spec?.name ?? "Strategy research"}</h3>
        <small>Market evidence: {basis?.market_observed_at ? new Date(basis.market_observed_at).toLocaleString() : "—"} · Historical provider: {basis?.historical_provider ?? "—"}</small>
        <span className="status">{item.state === "NO_TRADE" ? "NO QUALIFYING STRATEGY" : item.state.replaceAll("_", " ")}</span>
        {item.failure ? <p className="notice">Research failed: {String(item.failure)}{item.failure_detail ? ` · ${String(item.failure_detail)}` : ""}</p> : null}
        {item.rationale ? <p>{String(item.rationale)}</p> : null}
        <p className="muted">{item.state === "DEGRADED" ? "Research could not complete. Review the data connection and run a new cycle." : ["NO_TRADE", "NO_QUALIFYING_STRATEGY"].includes(item.state) ? "No hypothesis passed the preliminary screen. Review the research evidence before developing another strategy." : item.state === "AWAITING_STRATEGY_APPROVAL" ? "Review the proposed rules, then accept or reject the proposal. Formal validation and paper trading follow." : "Strategy rules and validation progress are available on the strategies page."}</p>
      </section>;
    })}</div> : <p className="muted">Strategy research starts as soon as top-pair selection completes.</p>}
    <Link className="btn" href="/strategies">View strategy evidence & validation</Link>
  </article>;
}
