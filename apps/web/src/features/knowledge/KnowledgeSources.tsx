"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type SearchResult = { query_hash: string; degraded: boolean; results: Array<{ source_id: string; segment_id: string; source_name: string; source_version: number; text: string; score: number }> };

export function KnowledgeSources() {
  const client = useQueryClient();
  const sources = useQuery<Resource[]>({ queryKey: ["knowledge", "sources"], queryFn: () => api("/knowledge/sources") });
  const health = useQuery<{state:string; active_sources:number; indexed_segments:number}>({ queryKey: ["knowledge", "health"], queryFn: () => api("/knowledge/health") });
  const [source,setSource]=useState({name:"",content:"",category:"general",tags:""});
  const [query,setQuery]=useState("");
  const [results,setResults]=useState<SearchResult|null>(null);
  const [message,setMessage]=useState("");
  const refresh=()=>client.invalidateQueries({queryKey:["knowledge"]});
  const create=useMutation({mutationFn:()=>api("/knowledge/sources",{method:"POST",body:JSON.stringify({...source,tags:source.tags.split(",").map(value=>value.trim()).filter(Boolean)})}),onSuccess:async()=>{setSource({name:"",content:"",category:"general",tags:""});setMessage("Source indexed with versioned chunks.");await refresh();},onError:(error:Error)=>setMessage(error.message)});
  const act=useMutation({mutationFn:({id,action}:{id:string;action:"reprocess"|"disable"|"delete"})=>action==="delete"?api(`/knowledge/sources/${id}`,{method:"DELETE"}):api(`/knowledge/sources/${id}/${action}`,{method:"POST",body:action==="reprocess"?JSON.stringify({name:String(sources.data?.find(item=>item.id===id)?.name??"Source"),content:source.content||"Reprocessed by operator",category:String(sources.data?.find(item=>item.id===id)?.category??"general")}):undefined}),onSuccess:refresh,onError:(error:Error)=>setMessage(error.message)});
  const search=useMutation({mutationFn:()=>api<SearchResult>("/knowledge/search",{method:"POST",body:JSON.stringify({query,limit:10})}),onSuccess:setResults,onError:(error:Error)=>setMessage(error.message)});
  const submit=(event:FormEvent)=>{event.preventDefault();setMessage("");create.mutate();};
  return <section className="section-stack"><header><p className="eyebrow">Context-only retrieval</p><h1>Knowledge sources</h1><p className="muted">Knowledge can explain and cite; it never overrides account, market, policy, risk, broker, or performance authority.</p></header>
    <div className="grid two"><form className="card form-stack" onSubmit={submit}><h2>Add source</h2><label>Name<input required value={source.name} onChange={e=>setSource({...source,name:e.target.value})}/></label><label>Category<input required value={source.category} onChange={e=>setSource({...source,category:e.target.value})}/></label><label>Tags<input placeholder="playbook, forex" value={source.tags} onChange={e=>setSource({...source,tags:e.target.value})}/></label><label>Content<textarea required rows={8} value={source.content} onChange={e=>setSource({...source,content:e.target.value})}/></label><button className="btn primary" disabled={create.isPending}>Ingest and index</button></form><article className="card"><h2>Index health</h2>{health.isPending?<p>Checking…</p>:<dl className="metric-list"><div><dt>State</dt><dd className={health.data?.state==="HEALTHY"?"good":"warn"}>{health.data?.state}</dd></div><div><dt>Active sources</dt><dd>{health.data?.active_sources}</dd></div><div><dt>Indexed segments</dt><dd>{health.data?.indexed_segments}</dd></div></dl>}</article></div>
    {message&&<p className="notice">{message}</p>}
    <article className="card"><h2>Owner-scoped sources</h2>{sources.isPending?<p>Loading…</p>:sources.data?.length?<div className="table-wrap"><table><thead><tr><th>Source</th><th>Category</th><th>Segments</th><th>State</th><th>Actions</th></tr></thead><tbody>{sources.data.map(item=><tr key={item.id}><td><strong>{String(item.name)}</strong><br/><small>v{String(item.generation)} · {String(item.content_hash).slice(0,10)}</small></td><td>{String(item.category)}</td><td>{String(item.segment_count)}</td><td>{item.state}</td><td><div className="actions"><button className="btn compact" disabled={act.isPending} onClick={()=>act.mutate({id:item.id,action:"reprocess"})}>Reprocess</button><button className="btn compact" disabled={act.isPending} onClick={()=>act.mutate({id:item.id,action:"disable"})}>Disable</button><button className="btn compact danger" disabled={act.isPending} onClick={()=>act.mutate({id:item.id,action:"delete"})}>Delete</button></div></td></tr>)}</tbody></table></div>:<p className="empty">No knowledge sources yet.</p>}</article>
    <form className="card form-stack" onSubmit={e=>{e.preventDefault();search.mutate();}}><h2>Audited hybrid search</h2><div className="actions"><input required placeholder="Search knowledge" value={query} onChange={e=>setQuery(e.target.value)}/><button className="btn primary" disabled={search.isPending}>Search</button></div>{results&&<><p className="muted">Query audit {results.query_hash.slice(0,12)} · {results.degraded?"degraded":"healthy"}</p>{results.results.length?<ol>{results.results.map(item=><li key={item.segment_id}><p>{item.text}</p><small>{item.source_name} · source v{item.source_version} · chunk {item.segment_id} · score {item.score.toFixed(3)}</small></li>)}</ol>:<p className="empty">No matching authorized chunks.</p>}</>}</form>
  </section>;
}
