"use client";

import { useQuery } from "@tanstack/react-query";
import { ProgressiveList } from "@/components/ProgressiveList";
import { Disclosure } from "@/components/Disclosure";
import { api } from "@/lib/api";

type Sample = { trade_count: number; average_r: number | null; win_rate: number | null; profit_factor_r: number | null; sharpe_per_trade?: number | null; sortino_per_trade?: number | null; max_drawdown_r?: number | null; trades_per_calendar_day?: number | null; complete?: boolean };
export type PairProfile = { regime_key: string; regime: { news: string }; candle_count: number; trend_efficiency: string; liquidity: { status: string }; news_sensitivity: { status: string }; limitations: string[] };
type LibraryEntry = { strategy_version_id: string; name: string; instrument: string; family: string; state: string; timeframe: string; account_id: string; profile?: PairProfile; regime_performance: Record<string, Sample>; recent: Sample; recent_basis: string; health: { status: string; reason: string; windows: Record<string, Sample> }; selection?: { selected_version_id?: string | null }; robustness: { available?: boolean; method?: string; research_selection_cut_at?: string | null; holdout_start_at?: string | null; history_depth_passed?: boolean; unseen_candle_count?: number; required_unseen_candles?: number } };

function value(number: number | null | undefined) {
  return number == null ? "Unavailable" : number.toFixed(3);
}

export function PairProfileSummary({ profile }: { profile?: PairProfile }) {
  if (!profile) return null;
  return <div className="inset form-stack">
    <h4>Pair profile</h4>
    <p>{profile.regime_key} · News: {profile.regime.news} · {profile.candle_count} completed candles</p>
    <p className="muted">Trend efficiency: {profile.trend_efficiency} · Liquidity: {profile.liquidity.status} · News sensitivity: {profile.news_sensitivity.status}</p>
    <details><summary>Evidence limitations</summary><ul>{profile.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
  </div>;
}

export function StrategyLibrary() {
  const library = useQuery<(LibraryEntry & { execution_validation?: { engine: string; status: string; passed: boolean; trade_count?: number; data_basis?: string } })[]>({ queryKey: ["strategies", "library"], queryFn: () => api("/strategies/library"), refetchInterval: 15000 });
  return <article className="card form-stack">
    <h2>Strategy–regime library</h2>
    <p>CFD research tests seven families in both directions alongside the agent’s hypotheses. Discovery-only vectorbt sweeps compare parameter regions; native NautilusTrader replay validates order lifecycle and costs before paper promotion. Selection requires passing robustness and paper validation, at least 10 positive out-of-sample trades in the current regime, and positive recorded forward performance.</p>
    <p className="muted">Rolling 30/60/100-trade windows monitor the simulated forward ledger. A complete window with non-positive expectancy suspends the active version. These observations are not broker executions.</p>
    {library.isError ? <p role="alert">Unable to load strategy evidence: {library.error.message}</p> : null}
    {!library.isError && !library.data?.length ? <p className="empty">Run formal backtesting to populate pair/regime performance evidence.</p> : null}
    <ProgressiveList items={library.data ?? []} label="library strategies">{visible => <>{visible.map(item => <section className="inset form-stack" key={item.strategy_version_id}>
      <h3>{item.instrument} · {item.family} · {item.state}</h3>
      <p className="muted">{item.name} · {item.timeframe ?? "Timeframe pending validation"} · Account {item.account_id ?? "unavailable"}</p>
      {item.profile ? <Disclosure title="Pair profile & evidence"><PairProfileSummary profile={item.profile} /></Disclosure> : null}
      {item.execution_validation ? <div className={`inset ${item.execution_validation.passed ? "good" : "warn"}`}><h4>Event-driven execution validation</h4><p>{item.execution_validation.engine ?? "NautilusTrader"} · {item.execution_validation.status} · {item.execution_validation.passed ? "Passed simulation gate" : "Not eligible for paper promotion"}</p><small>{item.execution_validation.trade_count ?? 0} simulated trades · {item.execution_validation.data_basis?.replaceAll("_", " ") ?? "Execution data basis unavailable"}. Simulation does not authorize broker orders.</small></div> : null}
      {item.robustness?.history_depth_passed === false ? <p className="notice">Waiting for independent history: {item.robustness.unseen_candle_count}/{item.robustness.required_unseen_candles} completed post-selection candles. Opted-in accounts retry automatically when more data is due.</p> : null}
      {item.robustness?.research_selection_cut_at ? <p className="muted">Research selection cut: {new Date(item.robustness.research_selection_cut_at).toLocaleString()} · Independent holdout: {item.robustness.holdout_start_at ? new Date(item.robustness.holdout_start_at).toLocaleString() : "Waiting for sufficient new candles"}</p> : null}
      <Disclosure title="Performance by regime"><div className="table-wrap"><table><thead><tr><th>Validated regime</th><th>OOS trades</th><th>Average R</th><th>Win rate</th><th>Profit factor (R)</th><th>Sharpe / Sortino</th><th>Max drawdown (R)</th><th>Trades / day</th></tr></thead><tbody>
        {Object.entries(item.regime_performance).map(([regime, sample]) => <tr key={regime}><td>{regime}</td><td>{sample.trade_count}</td><td>{value(sample.average_r)}</td><td>{sample.win_rate == null ? "Unavailable" : `${(sample.win_rate * 100).toFixed(1)}%`}</td><td>{value(sample.profit_factor_r)}</td><td>{value(sample.sharpe_per_trade)} / {value(sample.sortino_per_trade)}</td><td>{value(sample.max_drawdown_r)}</td><td>{value(sample.trades_per_calendar_day)}</td></tr>)}
      </tbody></table></div></Disclosure>
      <p>Recent: {item.recent.trade_count} trades · Average R {value(item.recent.average_r)} · {item.recent_basis.replaceAll("_", " ")}</p>
      <p>Health: {item.health.status} · {item.health.reason}</p>
      <ul>{Object.entries(item.health.windows).map(([size, sample]) => <li key={size}>Last {size}: {sample.trade_count}/{size} trades · Average R {value(sample.average_r)} · {sample.complete ? "complete" : "warming up"}</li>)}</ul>
      {item.selection ? <p>{item.selection.selected_version_id === item.strategy_version_id ? "Selected for the current regime; waiting for setup and risk checks." : item.selection.selected_version_id ? "Another eligible version ranks higher." : "No eligible strategy for the current regime."}</p> : null}
    </section>)}</>}</ProgressiveList>
  </article>;
}
