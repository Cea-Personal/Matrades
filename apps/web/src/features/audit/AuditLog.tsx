"use client";

import { useQuery } from "@tanstack/react-query";
import { ProgressiveList, newestFirst } from "@/components/ProgressiveList";
import { api } from "@/lib/api";

type AuditEvent = { id: string; event_type: string; aggregate_type: string; aggregate_id: string | null; actor_id: string | null; created_at: string };

export function AuditLog() {
  const audit = useQuery<AuditEvent[]>({ queryKey: ["operations", "audit"], queryFn: () => api("/operations/audit?limit=50"), refetchInterval: 10_000 });
  return <section><h2>Owner-scoped audit</h2>{audit.isPending ? <p>Loading audit chain…</p> : audit.data?.length ? <ProgressiveList items={newestFirst(audit.data)} label="audit events">{visible => <div className="table-wrap card"><table><thead><tr><th>Event</th><th>Aggregate</th><th>Actor</th><th>Recorded</th></tr></thead><tbody>{visible.map(item => <tr key={item.id}><td>{item.event_type}</td><td>{item.aggregate_type}<br/><small>{item.aggregate_id}</small></td><td>{item.actor_id ?? "system"}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>}</ProgressiveList> : <p className="empty card">No recorded events.</p>}</section>;
}
