"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

// Decision timeline is reconstructed from durable owner-scoped audit evidence.

type Journal = { events: Array<{ id: string; event_type: string; created_at: string; evidence: Record<string, unknown> }>; reconstructable: boolean };

export function JournalTimeline() {
  const proposals = useQuery<Resource[]>({ queryKey: ["trading", "proposals"], queryFn: () => api("/trade-proposals") });
  const [selected, setSelected] = useState("");
  const journal = useQuery<Journal>({ queryKey: ["operations", "journal", selected], queryFn: () => api(`/operations/journal/${selected}`), enabled: Boolean(selected) });
  return <section><h2>Decision reconstruction</h2><label>Proposal<select value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select an aggregate</option>{proposals.data?.map(item => <option key={item.id} value={item.id}>{String(item.instrument)} · {item.state}</option>)}</select></label>{selected && (journal.isPending ? <p>Reconstructing…</p> : journal.data?.events.length ? <ol className="card timeline">{journal.data.events.map(item => <li key={item.id}><strong>{item.event_type}</strong><small>{new Date(item.created_at).toLocaleString()}</small><pre>{JSON.stringify(item.evidence)}</pre></li>)}</ol> : <p className="empty card">No owner-scoped events for this aggregate.</p>)}</section>;
}
