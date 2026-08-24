"use client";

import { useState } from "react";

import { api } from "@/lib/api";

// Independent resolution contract: Agent → Orchestrator → Platform.

export function PromptConfiguration(){
  const [values,setValues]=useState({agentSystem:"",agentUser:"",orchestratorSystem:"",orchestratorUser:"",platformSystem:"Bounded Matrades specialist",platformUser:"Analyze structured evidence"});
  const [preview,setPreview]=useState<Record<string,string>|null>(null);
  const run=async()=>{const result=await api<Record<string,string>>("/agents/prompt-preview",{method:"POST",body:JSON.stringify({agent:{system:values.agentSystem||null,user:values.agentUser||null},orchestrator:{system:values.orchestratorSystem||null,user:values.orchestratorUser||null},platform:{system:values.platformSystem,user:values.platformUser}})});setPreview(result);};
  return <article className="card section-stack"><h2>Prompt resolution preview</h2><div className="form-grid"><label>Agent system override<textarea value={values.agentSystem} onChange={e=>setValues({...values,agentSystem:e.target.value})}/></label><label>Agent user override<textarea value={values.agentUser} onChange={e=>setValues({...values,agentUser:e.target.value})}/></label><label>Orchestrator system<textarea value={values.orchestratorSystem} onChange={e=>setValues({...values,orchestratorSystem:e.target.value})}/></label><label>Orchestrator user<textarea value={values.orchestratorUser} onChange={e=>setValues({...values,orchestratorUser:e.target.value})}/></label></div><button className="btn" onClick={()=>void run()}>Preview independent chains</button>{preview&&<dl className="metric-list"><div><dt>System source</dt><dd>{preview.system_source}</dd></div><div><dt>User source</dt><dd>{preview.user_source}</dd></div></dl>}</article>;
}
