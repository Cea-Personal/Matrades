"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

// Codex App Server is default; LiteLLM requires explicit assignment to LITELLM_GATEWAY.

export type ModelProfile = { id:string;name:string;runtime:"CODEX_APP_SERVER"|"LITELLM_GATEWAY";provider:string;model:string;fallback_profile_ids:string[];capabilities:string[];active:boolean };

export function ModelProfiles(){
  const client=useQueryClient();
  const profiles=useQuery<ModelProfile[]>({queryKey:["agents","profiles"],queryFn:()=>api("/agents/profiles")});
  const runtimes=useQuery<Array<{type:string;default:boolean;enabled:boolean;explicit_opt_in?:boolean}>>({queryKey:["agents","runtimes"],queryFn:()=>api("/agents/runtimes")});
  const [form,setForm]=useState({name:"",runtime:"CODEX_APP_SERVER",provider:"openai",model:"",fallback_profile_ids:[] as string[]});
  const [error,setError]=useState("");
  const save=useMutation({mutationFn:()=>api("/agents/profiles",{method:"POST",body:JSON.stringify({...form,capabilities:["structured_output","reasoning"],parameters:{},active:true})}),onSuccess:async()=>{setForm({...form,name:"",model:"",fallback_profile_ids:[]});await client.invalidateQueries({queryKey:["agents"]});},onError:(e:Error)=>setError(e.message)});
  const submit=(e:FormEvent)=>{e.preventDefault();setError("");save.mutate();};
  return <section className="section-stack"><header><p className="eyebrow">Runtime authority</p><h1>Agent runtimes & model profiles</h1><p className="muted">Codex App Server is the default. LiteLLM is used only by an explicitly assigned profile.</p></header><div className="grid two">{runtimes.data?.map(runtime=><article className="card" key={runtime.type}><h2>{runtime.type.replaceAll("_"," ")}</h2><span className={`status ${runtime.enabled?"healthy":"disabled"}`}>{runtime.enabled?"Enabled":"Disabled"}</span><p>{runtime.default?"Platform default":"Explicit opt-in only"}</p></article>)}</div><form className="card form-grid wide" onSubmit={submit}><h2 className="full">Create immutable model profile</h2><label>Name<input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label><label>Runtime<select value={form.runtime} onChange={e=>setForm({...form,runtime:e.target.value as typeof form.runtime})}><option>CODEX_APP_SERVER</option><option>LITELLM_GATEWAY</option></select></label><label>Provider<input required value={form.provider} onChange={e=>setForm({...form,provider:e.target.value})}/></label><label>Model<input required placeholder="Configured runtime model" value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/></label><label className="full">Same-runtime fallback<select multiple value={form.fallback_profile_ids} onChange={e=>setForm({...form,fallback_profile_ids:Array.from(e.target.selectedOptions).map(option=>option.value)})}>{profiles.data?.filter(item=>item.runtime===form.runtime).map(item=><option value={item.id} key={item.id}>{item.name} · {item.model}</option>)}</select></label><button className="btn primary" disabled={save.isPending}>Save profile version</button>{error&&<p className="notice bad">{error}</p>}</form><article className="card"><h2>Profile catalog</h2>{profiles.isPending?<p>Loading…</p>:profiles.data?.length?<div className="table-wrap"><table><thead><tr><th>Name</th><th>Runtime</th><th>Provider / model</th><th>Fallbacks</th></tr></thead><tbody>{profiles.data.map(item=><tr key={item.id}><td>{item.name}</td><td>{item.runtime}</td><td>{item.provider} / {item.model}</td><td>{item.fallback_profile_ids.length}</td></tr>)}</tbody></table></div>:<p className="empty">No profiles available.</p>}</article></section>;
}
