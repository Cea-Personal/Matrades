"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type Candidate = { instrument: string; category: string; score: number; evidence: string[]; fresh: boolean };
const starter = [
  { instrument: "", category: "forex", closes: "", macro: "0", event_risk: "0", sentiment: "0", positioning: "0", correlation: "0" },
  { instrument: "", category: "metals", closes: "", macro: "0", event_risk: "0", sentiment: "0", positioning: "0", correlation: "0" },
  { instrument: "", category: "crypto", closes: "", macro: "0", event_risk: "0", sentiment: "0", positioning: "0", correlation: "0" },
];

export function MarketSelection() {
  const queryClient = useQueryClient();
  const runs = useQuery<Resource[]>({ queryKey: ["research", "runs"], queryFn: () => api("/research/runs") });
  const selections = useQuery<Resource[]>({ queryKey: ["research", "selections"], queryFn: () => api("/research/selections") });
  const [rows, setRows] = useState(starter);
  const [replacement, setReplacement] = useState("");
  const [message, setMessage] = useState("");
  const latest = runs.data?.[0];
  const candidates = (latest?.candidates as Candidate[] | undefined) ?? [];
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["research"] });
  const run = useMutation({ mutationFn: () => api<Resource>("/research/runs", { method: "POST", body: JSON.stringify({ candidates: rows.map(row => ({ ...row, closes: row.closes.split(",").map(Number), macro: Number(row.macro), event_risk: Number(row.event_risk), sentiment: Number(row.sentiment), positioning: Number(row.positioning), correlation: Number(row.correlation), fresh: true, source_version: `operator-${new Date().toISOString()}` })) }) }), onSuccess: async () => { setMessage("Research completed with server-ranked evidence."); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const decide = useMutation({ mutationFn: (payload: Record<string, string>) => api(`/research/runs/${latest?.id}/decisions`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: async () => { setMessage("HIL-1 decision recorded."); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const submit = (event: FormEvent) => { event.preventDefault(); setMessage(""); run.mutate(); };
  return <section className="section-stack"><header><p className="eyebrow">Human-in-the-loop 1</p><h1>Session research</h1><p className="muted">Submit observed inputs; the server computes features, regimes, evidence and one ranked candidate per category.</p></header>
    <form className="card form-stack" onSubmit={submit}><h2>Candidate observations</h2>{rows.map((row,index)=><fieldset className="candidate-row" key={`${row.category}-${index}`}><legend>{row.category}</legend><label>Instrument<input required value={row.instrument} onChange={e=>setRows(rows.map((item,i)=>i===index?{...item,instrument:e.target.value}:item))}/></label><label>Closing prices<input required value={row.closes} onChange={e=>setRows(rows.map((item,i)=>i===index?{...item,closes:e.target.value}:item))}/></label><label>Macro<input type="number" min="-1" max="1" step="0.1" value={row.macro} onChange={e=>setRows(rows.map((item,i)=>i===index?{...item,macro:e.target.value}:item))}/></label><label>Event risk<input type="number" min="0" max="1" step="0.1" value={row.event_risk} onChange={e=>setRows(rows.map((item,i)=>i===index?{...item,event_risk:e.target.value}:item))}/></label><label>Sentiment<input type="number" min="-1" max="1" step="0.1" value={row.sentiment} onChange={e=>setRows(rows.map((item,i)=>i===index?{...item,sentiment:e.target.value}:item))}/></label></fieldset>)}<button className="btn primary" disabled={run.isPending}>{run.isPending?"Ranking…":"Run daily research"}</button></form>
    {message&&<p className="notice">{message}</p>}
    {runs.isPending?<p>Loading research…</p>:latest?<><div className="grid">{candidates.map(item=><article className="card" key={item.category}><p className="muted">{item.category}</p><h2>{item.instrument}</h2><strong className={item.fresh?"good":"bad"}>{item.fresh?item.score.toFixed(3):"DEGRADED"}</strong><ul>{item.evidence.map(value=><li key={value}>{value}</li>)}</ul><div className="actions"><input aria-label={`Replacement for ${item.category}`} placeholder="Replacement symbol" value={replacement} onChange={e=>setReplacement(e.target.value)}/><button className="btn" disabled={!replacement||decide.isPending} onClick={()=>decide.mutate({action:"REPLACE",category:item.category,instrument:replacement})}>Replace</button></div></article>)}</div><div className="actions"><button className="btn primary" disabled={latest.state!=="READY"||decide.isPending} onClick={()=>decide.mutate({action:"APPROVE"})}>Approve universe</button><button className="btn" disabled={decide.isPending} onClick={()=>decide.mutate({action:"NO_TRADE",reason:"Operator selected no trade"})}>No trade</button><button className="btn" disabled={decide.isPending} onClick={()=>decide.mutate({action:"RERUN"})}>Rerun</button></div></>:<p className="empty">No persisted research run yet.</p>}
    <article className="card"><h2>Recorded selections</h2>{selections.data?.length?<ul className="record-list">{selections.data.map(item=><li key={item.id}><strong>{String(item.action)}</strong><span>{Object.entries((item.selected as Record<string,string>)??{}).map(([key,value])=>`${key}: ${value}`).join(" · ")||"No trade"}</span><small>{new Date(item.created_at).toLocaleString()}</small></li>)}</ul>:<p className="empty">No HIL-1 decisions yet.</p>}</article>
  </section>;
}
