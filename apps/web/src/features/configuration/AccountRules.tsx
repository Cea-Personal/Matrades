"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, Resource, withStepUp } from "@/lib/api";
import { MfaDeleteDialog } from "@/components/MfaDeleteDialog";

type Limits = { contributors: Array<Record<string, unknown>>; effective: Record<string, Record<string, unknown>> };
type RemovalTarget = { id: string; label: string; scope: "broker.change" | "hard_rule.change"; path: string; message: string };
type MatrixLane = { asset_class: string; instrument_type: string; enabled: boolean };
type Matrix = { account_id: string; version: number; lanes: MatrixLane[]; schedule: Record<string, unknown> };

export function AccountRules() {
  const queryClient = useQueryClient();
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const rulesets = useQuery<Resource[]>({ queryKey: ["configuration", "rulesets"], queryFn: () => api("/configuration/prop-rulesets") });
  const guardrails = useQuery<Resource[]>({ queryKey: ["configuration", "guardrails"], queryFn: () => api("/configuration/guardrails") });
  const limits = useQuery<Limits>({ queryKey: ["configuration", "limits"], queryFn: () => api("/configuration/effective-limits") });
  const [matrixAccountId, setMatrixAccountId] = useState("");
  const selectedMatrixAccount = matrixAccountId || accounts.data?.[0]?.id || "";
  const matrix = useQuery<Matrix>({ queryKey: ["configuration", "matrix", selectedMatrixAccount], queryFn: () => api(`/accounts/${selectedMatrixAccount}/research-matrix`), enabled: Boolean(selectedMatrixAccount) });
  const [matrixDraft, setMatrixDraft] = useState<MatrixLane[] | null>(null);
  const [account, setAccount] = useState({ name: "", currency: "USD", kind: "PERSONAL", starting_balance: "" });
  const [rule, setRule] = useState({ name: "", kind: "MAX_TOTAL_DRAWDOWN", value: "", source_reference: "", target: "guardrail" });
  const [message, setMessage] = useState("");
  const [removalTarget, setRemovalTarget] = useState<RemovalTarget | null>(null);
  const activeAccounts = (accounts.data ?? []).filter(item => item.state !== "DELETED");
  const activeContributors = [...(rulesets.data ?? []).map(item => ({ ...item, contributorKind: "prop-rulesets" as const })), ...(guardrails.data ?? []).map(item => ({ ...item, contributorKind: "guardrails" as const }))].filter(item => item.state === "ACTIVE");

  const createAccount = useMutation({
    mutationFn: () => api("/configuration/accounts", { method: "POST", body: JSON.stringify(account) }),
    onSuccess: async () => { setAccount({ ...account, name: "", starting_balance: "" }); await queryClient.invalidateQueries({ queryKey: ["configuration"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const createRule = useMutation({
    mutationFn: () => api(`/configuration/${rule.target === "guardrail" ? "guardrails" : "prop-rulesets"}`, {
      method: "POST",
      body: JSON.stringify({ name: rule.name, source_reference: rule.source_reference || null, verified: true, active: true, rules: [{ kind: rule.kind, value: rule.value, unit: "account_currency", enforcement: "HARD" }] }),
    }),
    onSuccess: async () => { setRule({ ...rule, name: "", value: "", source_reference: "" }); await queryClient.invalidateQueries({ queryKey: ["configuration"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const removeTarget = useMutation({
    mutationFn: async (code: string) => {
      if (!removalTarget) throw new Error("Choose an item to remove");
      return withStepUp(removalTarget.scope, code, grant => api(removalTarget.path, {
        method: "DELETE",
        headers: { "Step-Up-Grant": grant },
      }));
    },
    onSuccess: async () => {
      setMessage(removalTarget?.message ?? "Removed from active configuration; its audit history is retained.");
      setRemovalTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["configuration"] });
    },
    onError: (error: Error) => setMessage(error.message),
  });
  const saveMatrix = useMutation({
    mutationFn: () => api(`/accounts/${selectedMatrixAccount}/research-matrix`, { method: "PUT", body: JSON.stringify({ lanes: matrixDraft ?? matrix.data?.lanes ?? [], schedule: matrix.data?.schedule ?? {} }) }),
    onSuccess: async () => { setMessage("Research matrix version activated for this account."); setMatrixDraft(null); await queryClient.invalidateQueries({ queryKey: ["configuration", "matrix"] }); },
    onError: (error: Error) => setMessage(error.message),
  });

  const submitAccount = (event: FormEvent) => { event.preventDefault(); setMessage(""); createAccount.mutate(); };
  const submitRule = (event: FormEvent) => { event.preventDefault(); setMessage(""); createRule.mutate(); };

  return <section className="section-stack"><header><p className="eyebrow">Risk authority</p><h1>Accounts & rules</h1><p className="muted">Current equity and the strictest active prop or internal rule govern every proposal.</p><p className="muted">Removing an account or active risk contributor opens an MFA confirmation dialog. Removals are soft-deleted so audit history remains available.</p></header>
    <div className="grid two"><form className="card form-stack" onSubmit={submitAccount}><h2>Add trading account</h2><label>Name<input required value={account.name} onChange={e=>setAccount({...account,name:e.target.value})}/></label><div className="form-grid"><label>Currency<input required maxLength={3} value={account.currency} onChange={e=>setAccount({...account,currency:e.target.value.toUpperCase()})}/></label><label>Type<select value={account.kind} onChange={e=>setAccount({...account,kind:e.target.value})}><option>PERSONAL</option><option>PROP</option></select></label></div><label>Starting balance<input required type="number" min="1" step="0.01" value={account.starting_balance} onChange={e=>setAccount({...account,starting_balance:e.target.value})}/></label><button className="btn primary" disabled={createAccount.isPending}>Save account</button></form>
      <form className="card form-stack" onSubmit={submitRule}><h2>Add hard limit</h2><label>Policy layer<select value={rule.target} onChange={e=>setRule({...rule,target:e.target.value})}><option value="guardrail">Internal guardrail</option><option value="prop">Prop-firm ruleset</option></select></label><label>Name<input required value={rule.name} onChange={e=>setRule({...rule,name:e.target.value})}/></label><label>Constraint<select value={rule.kind} onChange={e=>setRule({...rule,kind:e.target.value})}><option>MAX_TOTAL_DRAWDOWN</option><option>MAX_DAILY_LOSS</option><option>MAX_PORTFOLIO_RISK</option><option>MAX_CORRELATED_RISK</option><option>MAX_CONCURRENT_TRADES</option></select></label><label>Value<input required type="number" min="0" step="0.01" value={rule.value} onChange={e=>setRule({...rule,value:e.target.value})}/></label><label>Source reference<input value={rule.source_reference} onChange={e=>setRule({...rule,source_reference:e.target.value})}/></label><button className="btn primary" disabled={createRule.isPending}>Activate version</button></form></div>
    {message&&<p className="notice bad">{message}</p>}
    <article className="card"><h2>Configured accounts</h2>{accounts.isPending?<p>Loading…</p>:activeAccounts.length?<div className="table-wrap"><table><thead><tr><th>Name</th><th>Account ID</th><th>Type</th><th>Currency</th><th>Starting balance</th><th>Version</th><th /></tr></thead><tbody>{activeAccounts.map(item=><tr key={item.id}><td>{String(item.name)}</td><td><code>{item.id}</code></td><td>{String(item.kind)}</td><td>{String(item.currency)}</td><td>{String(item.starting_balance)}</td><td>{item.version}</td><td><button className="btn compact" disabled={removeTarget.isPending} onClick={()=>setRemovalTarget({ id: String(item.id), label: String(item.name), scope: "broker.change", path: `/configuration/accounts/${item.id}`, message: "Trading account removed from active configuration; its audit history is retained." })}>Remove</button></td></tr>)}</tbody></table></div>:<p className="empty">No active trading accounts yet.</p>}</article>
    <article className="card form-stack"><h2>Account research matrix</h2><p className="muted">Enable or disable each asset-class × instrument-type lane. The matrix is versioned and does not infer a type from a symbol.</p>{activeAccounts.length ? <><label>Trading account<select value={selectedMatrixAccount} onChange={event => { setMatrixAccountId(event.target.value); setMatrixDraft(null); }}><option value="">Select account</option>{activeAccounts.map(item => <option key={item.id} value={item.id}>{String(item.name)}</option>)}</select></label>{(matrixDraft ?? matrix.data?.lanes ?? []).map((lane, index) => <label key={`${lane.asset_class}:${lane.instrument_type}`}><input type="checkbox" checked={lane.enabled} onChange={event => setMatrixDraft((matrixDraft ?? matrix.data?.lanes ?? []).map((item, itemIndex) => itemIndex === index ? { ...item, enabled: event.target.checked } : item))} /> {lane.asset_class} · {lane.instrument_type}</label>)}<button className="btn primary" disabled={!selectedMatrixAccount || saveMatrix.isPending || !(matrixDraft ?? matrix.data?.lanes)?.some(item => item.enabled)} onClick={() => saveMatrix.mutate()}>{saveMatrix.isPending ? "Saving…" : `Activate matrix v${(matrix.data?.version ?? 0) + 1}`}</button></> : <p className="empty">Configure a trading account first.</p>}</article>
    <div className="grid two"><article className="card"><h2>Active contributors</h2>{activeContributors.length?<ul className="record-list">{activeContributors.map(item=><li key={item.id}><strong>{String((item as Resource).name)}</strong><span className={`status ${item.state.toLowerCase()}`}>{item.state}</span><small>v{item.version} · {item.contributorKind === "guardrails" ? "Internal guardrail" : "Prop-firm ruleset"}</small><button className="btn compact" disabled={removeTarget.isPending} onClick={()=>setRemovalTarget({ id: String(item.id), label: String((item as Resource).name), scope: "hard_rule.change", path: `/configuration/${item.contributorKind}/${item.id}`, message: "Risk contributor removed from active limits; its audit history is retained." })}>Remove</button></li>)}</ul>:<p className="empty">No active rules. Risk decisions will fail closed.</p>}</article><article className="card"><h2>Effective limits</h2>{Object.entries(limits.data?.effective??{}).length?<dl className="metric-list">{Object.entries(limits.data?.effective??{}).map(([kind,value])=><div key={kind}><dt>{kind.replaceAll("_"," ")}</dt><dd>{String(value.value)} <small>{String(value.source)} · v{String(value.version)}</small></dd></div>)}</dl>:<p className="empty">No complete effective policy.</p>}<p className="notice warn">Strictest applicable value governs.</p></article></div>
    {removalTarget ? <MfaDeleteDialog key={removalTarget.id} targetLabel={removalTarget.label} scope={removalTarget.scope} busy={removeTarget.isPending} error={removeTarget.error instanceof Error ? removeTarget.error.message : undefined} onCancel={() => setRemovalTarget(null)} onConfirm={code => removeTarget.mutate(code)} /> : null}
  </section>;
}
