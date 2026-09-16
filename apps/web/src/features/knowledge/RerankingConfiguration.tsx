"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type Configuration = {
  configured: boolean;
  connection_id: string | null;
  model: string;
  candidate_limit: number;
  verified_at: string | null;
};

export type RerankingMetadata = {
  status: "DISABLED" | "SKIPPED" | "APPLIED" | "DEGRADED";
  model?: string | null;
  candidate_count?: number;
  reason?: string;
};

export function RerankingStatus({ result }: { result?: RerankingMetadata }) {
  if (!result) return null;
  if (result.status === "DEGRADED") return <p className="notice warn" role="status">Cohere reranking unavailable; results use hybrid retrieval order.</p>;
  return <p className="muted">{result.status === "APPLIED" ? `Reranked with ${result.model} · ${result.candidate_count} candidates` : result.status === "SKIPPED" ? "No matching candidates to rerank." : "Hybrid retrieval · reranking disabled"}</p>;
}

export function RerankingConfiguration({ connections }: { connections: Resource[] }) {
  const client = useQueryClient();
  const configuration = useQuery<Configuration>({ queryKey: ["knowledge", "reranking-configuration"], queryFn: () => api("/knowledge/reranking-configuration") });
  const [draft, setDraft] = useState<Configuration | null>(null);
  const [message, setMessage] = useState("");
  const editable = draft ?? configuration.data;
  const available = connections.filter(item => item.provider === "COHERE" && item.active !== false && !["DELETED", "DISABLED"].includes(item.state));
  const update = (patch: Partial<Configuration>) => { if (editable) setDraft({ ...editable, ...patch }); };
  const saved = async (value: Configuration) => {
    client.setQueryData(["knowledge", "reranking-configuration"], value);
    setDraft(null);
    setMessage(value.configured ? "Cohere verified. Knowledge search and assistant retrieval now use reranking." : "Reranking disabled. Knowledge retrieval uses hybrid scoring only.");
    await client.invalidateQueries({ queryKey: ["knowledge", "health"] });
  };
  const save = useMutation({
    mutationFn: () => {
      if (!editable?.connection_id) throw new Error("Select an active Cohere connection first");
      return api<Configuration>("/knowledge/reranking-configuration", { method: "PUT", body: JSON.stringify({ connection_id: editable.connection_id, model: editable.model, candidate_limit: editable.candidate_limit }) });
    },
    onSuccess: saved,
    onError: (error: Error) => setMessage(error.message),
  });
  const disable = useMutation({
    mutationFn: () => api<Configuration>("/knowledge/reranking-configuration", { method: "DELETE" }),
    onSuccess: saved,
    onError: (error: Error) => setMessage(error.message),
  });
  const busy = save.isPending || disable.isPending;

  return <article className="card form-stack">
    <h2>Cohere knowledge reranking</h2>
    <p className="muted">Optional second-stage ranking after hybrid search. Enabling sends your query and owner-authorized candidate text to Cohere before the final citations are selected. Documents keep their existing embeddings; no re-indexing is needed.</p>
    {configuration.isError ? <p className="notice bad">Unable to load reranking configuration.</p> : editable ? <form className="form-stack" onSubmit={event => { event.preventDefault(); setMessage(""); save.mutate(); }}>
      <label>Cohere connection<select required disabled={busy} value={editable.connection_id ?? ""} onChange={event => update({ connection_id: event.target.value })}>
        <option value="">Select an active Cohere connection</option>
        {editable.connection_id && !available.some(item => item.id === editable.connection_id) ? <option value={editable.connection_id} disabled>Saved connection unavailable — select another</option> : null}
        {available.map(item => <option key={item.id} value={item.id}>{String(item.name)} · {String(item.health ?? "UNTESTED")}</option>)}
      </select></label>
      <div className="form-grid">
        <label>Rerank model<select disabled={busy} value={editable.model} onChange={event => update({ model: event.target.value })}>
          <option value="rerank-v4.0-pro">rerank-v4.0-pro</option>
          <option value="rerank-v4.0-fast">rerank-v4.0-fast</option>
          <option value="rerank-v3.5">rerank-v3.5</option>
        </select></label>
        <label>Candidate pool<input required disabled={busy} type="number" min="20" max="100" step="1" value={editable.candidate_limit} onChange={event => update({ candidate_limit: Number(event.target.value) })} /></label>
      </div>
      <p className="muted">The best 20–100 hybrid matches are considered; search still returns only the requested number of citations. Verification makes a small, billable request using synthetic text. If Cohere fails, results retain hybrid ordering and show a degraded-retrieval warning.</p>
      <div className="actions">
        <button className="btn primary" disabled={busy || !available.some(item => item.id === editable.connection_id)}>{save.isPending ? "Verifying…" : "Verify and enable reranking"}</button>
        {configuration.data?.configured ? <button type="button" className="btn" disabled={busy} onClick={() => { setMessage(""); disable.mutate(); }}>{disable.isPending ? "Disabling…" : "Disable reranking"}</button> : null}
      </div>
      <small>{configuration.data?.configured ? `Enabled · ${configuration.data.model} · verified ${configuration.data.verified_at ? new Date(configuration.data.verified_at).toLocaleString() : "—"}` : "Disabled · hybrid retrieval remains active"}</small>
    </form> : <p>Loading reranking configuration…</p>}
    {!available.length ? <p className="notice warn">Add an encrypted Cohere API key and connection on the <Link href="/connections">Connections page</Link> first.</p> : null}
    {message ? <p className="notice" role="status">{message}</p> : null}
  </article>;
}
