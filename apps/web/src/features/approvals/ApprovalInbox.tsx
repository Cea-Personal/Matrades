"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type Approvals = { "HIL-1": Resource[]; "HIL-2": Resource[]; "HIL-3": Resource[] };

export function ApprovalInbox() {
  const inbox = useQuery<Approvals>({ queryKey: ["operations", "approvals"], queryFn: () => api("/operations/approvals"), refetchInterval: 10_000 });
  return <section><h2>Approval inbox</h2>{inbox.isPending ? <p>Loading approvals…</p> : <div className="grid">{(["HIL-1", "HIL-2", "HIL-3"] as const).map(level => <article className="card" key={level}><strong>{level}</strong><p className={(inbox.data?.[level].length ?? 0) > 0 ? "warn" : "muted"}>{inbox.data?.[level].length ?? 0} awaiting review</p><Link className="btn" href={level === "HIL-1" ? "/research" : "/trading"}>Open queue</Link></article>)}</div>}</section>;
}
