"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

// Decision timeline is reconstructed from durable owner-scoped audit evidence.

type Journal = { events: Array<{ id: string; event_type: string; created_at: string; evidence: Record<string, unknown> }>; reconstructable: boolean };

export function JournalTimeline() {
  const plans = useQuery<Resource[]>({ queryKey: ["automation", "plans"], queryFn: () => api("/automation/trade-plans") });
  const [selected, setSelected] = useState("");
  const journal = useQuery<Journal>({ queryKey: ["operations", "journal", selected], queryFn: () => api(`/operations/journal/${selected}`), enabled: Boolean(selected) });
  return <section><h2>Live trade journal</h2><p className="muted">Select an autonomous Trade Plan to inspect its durable audit timeline.</p><label>Trade Plan<select value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select a Trade Plan</option>{plans.data?.map(item => <option key={item.id} value={item.id}>{String(item.instrument ?? item.id)} · {item.state}</option>)}</select></label>{selected && (journal.isPending ? <p>Reconstructing…</p> : journal.data?.events.length ? <ol className="card timeline">{journal.data.events.map(item => <li key={item.id}><strong>{item.event_type}</strong><small>{new Date(item.created_at).toLocaleString()}</small><pre>{JSON.stringify(item.evidence)}</pre></li>)}</ol> : <p className="empty card">No owner-scoped events for this Trade Plan.</p>)}</section>;
}
