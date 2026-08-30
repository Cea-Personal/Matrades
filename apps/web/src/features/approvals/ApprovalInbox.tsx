"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type Operations = { trade_plans: Resource[]; execution_commands: Resource[]; active_trades: Resource[]; human_approval_required: boolean };

export function ApprovalInbox() {
  const operations = useQuery<Operations>({ queryKey: ["automation", "operations"], queryFn: () => api("/automation/operations"), refetchInterval: 10_000 });
  const plans = operations.data?.trade_plans ?? [];
  const commands = operations.data?.execution_commands ?? [];
  return <section><h2>Automation monitor</h2><p className="muted">Execution is governed by Trade Plan validation, account permissions, risk capacity, and kill switches. No manual approval queue is used.</p><div className="grid three"><article className="card"><strong>Plans</strong><p className="value">{plans.length}</p></article><article className="card"><strong>Commands</strong><p className="value">{commands.length}</p></article><article className="card"><strong>Open positions</strong><p className="value">{operations.data?.active_trades.length ?? 0}</p></article></div><article className="card"><h3>Latest execution states</h3>{commands.length === 0 ? <p className="empty">No commands have been dispatched.</p> : <ul className="record-list">{commands.slice(0, 8).map(command => <li key={command.id}><strong>{String(command.action ?? "Command")}</strong><span>{String(command.state)} · {String(command.outcome_certainty ?? "unknown")}</span><small>{String(command.broker_order_id ?? "Awaiting broker outcome")}</small></li>)}</ul>}</article></section>;
}
