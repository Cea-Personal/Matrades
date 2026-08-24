"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// Operational health is measured and refreshed; it is not a fixture.

type Health = { state: string; components: Array<{ component: string; state: string; fresh: boolean; latency_ms?: number | null }> };

export function HealthDashboard() {
  const health = useQuery<Health>({ queryKey: ["operations", "health"], queryFn: () => api("/operations/health"), refetchInterval: 15_000 });
  return <section><h2>Measured operational health</h2>{health.isPending ? <p>Checking dependencies…</p> : health.isError ? <p className="notice bad">Health unavailable: {health.error.message}</p> : <><p className={health.data?.state === "HEALTHY" ? "good" : "warn"}>Platform {health.data?.state}</p><div className="grid">{health.data?.components.map(item => <article className="card" key={item.component}><strong>{item.component}</strong><p className={item.state === "HEALTHY" && item.fresh ? "good" : "warn"}>{item.state} · {item.fresh ? "fresh" : "stale"}</p>{item.latency_ms != null && <small>{item.latency_ms} ms</small>}</article>)}</div></>}</section>;
}
