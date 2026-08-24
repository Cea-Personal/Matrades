"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type Approvals = { "HIL-1": Resource[]; "HIL-2": Resource[]; "HIL-3": Resource[] };
type Health = { state: string; components: Array<{ component: string; state: string }> };

export default function Dashboard() {
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const proposals = useQuery<Resource[]>({ queryKey: ["trading", "proposals"], queryFn: () => api("/trade-proposals") });
  const trades = useQuery<Resource[]>({ queryKey: ["trading", "active"], queryFn: () => api("/trade-management/trades") });
  const approvals = useQuery<Approvals>({ queryKey: ["operations", "approvals"], queryFn: () => api("/operations/approvals"), refetchInterval: 10_000 });
  const health = useQuery<Health>({ queryKey: ["operations", "health"], queryFn: () => api("/operations/health"), refetchInterval: 15_000 });
  const approvalCount = Object.values(approvals.data ?? {}).reduce((sum, items) => sum + items.length, 0);
  const cards = [["Trading accounts", String(accounts.data?.length ?? 0)], ["Active broker trades", String(trades.data?.length ?? 0)], ["Persisted proposals", String(proposals.data?.length ?? 0)], ["Approval inbox", String(approvalCount)]] as const;
  return <section className="section-stack"><header><p className="eyebrow">Operations / Overview</p><h1>Trading command center</h1><p className="muted">Owner-scoped authoritative state, bounded recommendations, and human approval.</p></header><section className="grid" aria-label="Account summary">{cards.map(([label,value])=><article className="card" key={label}><div className="muted">{label}</div><div className="value">{value}</div></article>)}</section><section className="card"><h2>Safety state</h2>{health.isPending?<p>Measuring dependencies…</p>:<><p className={health.data?.state==="HEALTHY"?"good":"warn"}>{health.data?.state}</p><p className="muted">{health.data?.components.map(item=>`${item.component}: ${item.state}`).join(" · ")}</p></>}<p className="muted">Broker actions remain read-only. TAKE and APPROVE record manual intent only.</p></section></section>;
}
