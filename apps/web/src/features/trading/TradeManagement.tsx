"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";
import { ActiveTradeChart } from "@/features/trading/ActiveTradeChart";

type Operations = {
  trade_plans: Resource[];
  execution_commands: Resource[];
  active_trades: Resource[];
  execution_mode: string;
};

function text(value: unknown, fallback = "—") {
  return value == null || value === "" ? fallback : String(value);
}

export function TradeManagement() {
  const operations = useQuery<Operations>({
    queryKey: ["automation", "operations"],
    queryFn: () => api("/automation/operations"),
    refetchInterval: 10_000,
  });
  const plans = operations.data?.trade_plans ?? [];
  const commands = operations.data?.execution_commands ?? [];
  const trades = operations.data?.active_trades ?? [];

  return (
    <section className="section-stack">
      <header>
        <h1>Autonomous trade operations</h1>
        <p className="muted">
          Trade Plans are validated against live account equity, permissions, and kill switches before
          commands are dispatched. This view is an operational monitor, not an approval queue.
        </p>
      </header>
      {operations.isError && <p className="notice bad">Unable to load autonomous operations.</p>}
      <div className="grid three">
        <article className="card"><div className="muted">Execution mode</div><div className="value">{text(operations.data?.execution_mode, "AUTONOMOUS")}</div></article>
        <article className="card"><div className="muted">Active positions</div><div className="value">{trades.length}</div></article>
        <article className="card"><div className="muted">Commands</div><div className="value">{commands.length}</div></article>
      </div>
      <article className="card">
        <h2>Active trades and their Trade Plans</h2>
        {operations.isPending ? <p>Loading live broker state…</p> : trades.length === 0 ? <p className="empty">No active broker positions.</p> : (
          <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Position</th><th>Plan</th><th>Risk / P&amp;L</th><th>Chart</th></tr></thead><tbody>
            {trades.map(trade => {
              const position = (trade.broker_position as Record<string, unknown> | undefined) ?? {};
              const instrument = text(position.instrument, text(trade.instrument, trade.id));
              const plan = plans.find(item => item.id === trade.trade_plan_id || item.instrument === instrument);
              return <tr key={trade.id}><td><strong>{instrument}</strong><small>{text(position.direction, "Direction unavailable")}</small></td><td>{text(trade.state)}<small>P&amp;L {text(position.pnl)}</small></td><td>{plan ? <><strong>{text(plan.state)}</strong><small>Risk {text((plan.risk as Record<string, unknown> | undefined)?.decision)}</small></> : "No linked plan"}</td><td>{text(position.pnl)}<small>Stop {text(position.stop_loss)}</small></td><td><a className="btn compact" href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(instrument)}`} target="_blank" rel="noreferrer">Open chart</a></td></tr>;
            })}
          </tbody></table></div>
        )}
      </article>
      {trades.map(trade => <ActiveTradeChart key={`chart-${trade.id}`} trade={trade} />)}
      <article className="card"><h2>Trade Plan lifecycle</h2>{plans.length === 0 ? <p className="empty">No autonomous Trade Plans recorded.</p> : <ul className="record-list">{plans.map(plan => <li key={plan.id}><strong>{text(plan.instrument, plan.id)}</strong><span>{text(plan.state)} · risk {text((plan.risk as Record<string, unknown> | undefined)?.decision)}</span><small>{new Date(plan.updated_at).toLocaleString()}</small></li>)}</ul>}</article>
      <article className="card"><h2>Execution command ledger</h2>{commands.length === 0 ? <p className="empty">No execution commands recorded.</p> : <div className="table-wrap"><table><thead><tr><th>Action</th><th>State</th><th>Outcome certainty</th><th>Broker order</th><th>Idempotency</th></tr></thead><tbody>{commands.map(command => <tr key={command.id}><td>{text(command.action)}</td><td>{text(command.state)}</td><td>{text(command.outcome_certainty)}</td><td>{text(command.broker_order_id)}</td><td><code>{text(command.idempotency_key)}</code></td></tr>)}</tbody></table></div>}</article>
    </section>
  );
}
