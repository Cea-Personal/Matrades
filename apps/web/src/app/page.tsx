"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type Health = { state: string; components: Array<{ component: string; state: string }> };
type Operations = { trade_plans: Resource[]; execution_commands: Resource[]; active_trades: Resource[]; execution_mode: string };

export default function Dashboard() {
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const operations = useQuery<Operations>({ queryKey: ["automation", "operations"], queryFn: () => api("/automation/operations"), refetchInterval: 10_000 });
  const health = useQuery<Health>({ queryKey: ["operations", "health"], queryFn: () => api("/operations/health"), refetchInterval: 15_000 });
  const cards = [["Trading accounts", accounts.data?.length ?? 0], ["Active broker trades", operations.data?.active_trades.length ?? 0], ["Trade Plans", operations.data?.trade_plans.length ?? 0], ["Execution commands", operations.data?.execution_commands.length ?? 0]] as const;
  return <section className="section-stack"><header><p className="eyebrow">Operations / Overview</p><h1>Autonomous trading command center</h1><p className="muted">Evidence, live account equity, policy constraints, and broker execution state in one owner-scoped view.</p></header><section className="grid" aria-label="Account summary">{cards.map(([label, value]) => <article className="card" key={label}><div className="muted">{label}</div><div className="value">{value}</div></article>)}</section><section className="card"><h2>Safety state</h2>{health.isPending ? <p>Measuring dependencies…</p> : <><p className={health.data?.state === "HEALTHY" ? "good" : "warn"}>{health.data?.state}</p><p className="muted">{health.data?.components.map(item => `${item.component}: ${item.state}`).join(" · ")}</p></>}<p className="muted">Execution mode: {operations.data?.execution_mode ?? "loading"}. Trade commands remain subject to permission profiles, risk revalidation, and kill switches.</p></section></section>;
}
