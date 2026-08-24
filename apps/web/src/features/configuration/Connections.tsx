"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, Resource } from "@/lib/api";

// Secret display is always masked as •••• and replacement requires step-up.

export function Connections() {
  const client = useQueryClient();
  const credentials = useQuery<Resource[]>({ queryKey: ["configuration", "credentials"], queryFn: () => api("/configuration/credentials") });
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const [credential, setCredential] = useState({ name: "", provider: "", purpose: "market_data", secret: "" });
  const [connection, setConnection] = useState({ name: "", provider: "", credential_id: "" });
  const [error, setError] = useState("");
  const invalidate = () => client.invalidateQueries({ queryKey: ["configuration"] });
  const createCredential = useMutation({ mutationFn:()=>api("/configuration/credentials",{method:"POST",body:JSON.stringify(credential)}), onSuccess:async()=>{setCredential({...credential,name:"",secret:""});await invalidate();},onError:(e:Error)=>setError(e.message)});
  const createConnection = useMutation({ mutationFn:()=>api("/configuration/connections",{method:"POST",body:JSON.stringify({...connection,credential_id:connection.credential_id||null,configuration:{}})}),onSuccess:async()=>{setConnection({...connection,name:""});await invalidate();},onError:(e:Error)=>setError(e.message)});
  const testConnection = useMutation({mutationFn:(id:string)=>api(`/configuration/connections/${id}/test`,{method:"POST"}),onSuccess:invalidate,onError:(e:Error)=>setError(e.message)});
  const submitCredential=(e:FormEvent)=>{e.preventDefault();setError("");createCredential.mutate();};
  const submitConnection=(e:FormEvent)=>{e.preventDefault();setError("");createConnection.mutate();};
  return <section className="section-stack"><header><p className="eyebrow">Provider boundary</p><h1>Connections & credentials</h1><p className="muted">Secrets are envelope-encrypted and never returned to the browser after entry.</p></header><div className="grid two"><form className="card form-stack" onSubmit={submitCredential}><h2>Store credential</h2><label>Name<input required value={credential.name} onChange={e=>setCredential({...credential,name:e.target.value})}/></label><label>Provider<input required value={credential.provider} onChange={e=>setCredential({...credential,provider:e.target.value})}/></label><label>Purpose<input required value={credential.purpose} onChange={e=>setCredential({...credential,purpose:e.target.value})}/></label><label>Secret<input required type="password" value={credential.secret} onChange={e=>setCredential({...credential,secret:e.target.value})}/></label><button className="btn primary" disabled={createCredential.isPending}>Encrypt credential</button></form><form className="card form-stack" onSubmit={submitConnection}><h2>Add connection</h2><label>Name<input required value={connection.name} onChange={e=>setConnection({...connection,name:e.target.value})}/></label><label>Provider<input required value={connection.provider} onChange={e=>setConnection({...connection,provider:e.target.value})}/></label><label>Credential<select value={connection.credential_id} onChange={e=>setConnection({...connection,credential_id:e.target.value})}><option value="">No credential</option>{credentials.data?.map(item=><option key={item.id} value={item.id}>{String(item.name)} · {String(item.masked_suffix)}</option>)}</select></label><button className="btn primary" disabled={createConnection.isPending}>Create connection</button></form></div>{error&&<p className="notice bad">{error}</p>}<article className="card"><h2>Provider connections</h2>{connections.isPending?<p>Loading…</p>:connections.data?.length?<div className="table-wrap"><table><thead><tr><th>Name</th><th>Provider</th><th>Health</th><th>Last success</th><th></th></tr></thead><tbody>{connections.data.map(item=><tr key={item.id}><td>{String(item.name)}</td><td>{String(item.provider)}</td><td><span className={`status ${String(item.health).toLowerCase()}`}>{String(item.health)}</span></td><td>{String(item.last_success??"Never")}</td><td><button className="btn compact" onClick={()=>testConnection.mutate(item.id)}>Test</button></td></tr>)}</tbody></table></div>:<p className="empty">No provider connections configured.</p>}</article></section>;
}
