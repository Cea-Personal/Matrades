"use client";

import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/providers";

export function SecuritySettings() {
  const { user } = useAuth();
  const [code,setCode]=useState("");
  const [scope,setScope]=useState("credential.change");
  const [grant,setGrant]=useState<{grant_id:string;expires_at:string}|null>(null);
  const [error,setError]=useState("");
  const submit=async(e:FormEvent)=>{e.preventDefault();setError("");try{const result=await api<{grant_id:string;expires_at:string}>("/auth/step-up",{method:"POST",body:JSON.stringify({action_scope:scope,code})});setGrant(result);sessionStorage.setItem("matrades_step_up",result.grant_id);setCode("");}catch(reason){setError(reason instanceof Error?reason.message:"Step-up failed");}};
  return <section className="section-stack"><header><p className="eyebrow">Identity</p><h1>Security</h1></header><div className="grid two"><article className="card"><h2>Account activation</h2><dl className="metric-list"><div><dt>Email</dt><dd>{user?.email}</dd></div><div><dt>Email verified</dt><dd className={user?.email_verified?"good":"bad"}>{user?.email_verified?"Yes":"No"}</dd></div><div><dt>MFA enrolled</dt><dd className={user?.mfa_enabled?"good":"bad"}>{user?.mfa_enabled?"Yes":"No"}</dd></div><div><dt>Role</dt><dd>{user?.role}</dd></div></dl></article><form className="card form-stack" onSubmit={submit}><h2>Sensitive-action step-up</h2><label>Action scope<select value={scope} onChange={e=>setScope(e.target.value)}><option>credential.change</option><option>security.change</option><option>broker.change</option><option>hard_rule.change</option><option>guardrail.reduce</option></select></label><label>Authenticator or recovery code<input required value={code} onChange={e=>setCode(e.target.value)}/></label><button className="btn primary">Verify step-up</button>{grant&&<p className="notice good">Grant available until {new Date(grant.expires_at).toLocaleTimeString()}.</p>}{error&&<p className="notice bad">{error}</p>}</form></div></section>;
}
