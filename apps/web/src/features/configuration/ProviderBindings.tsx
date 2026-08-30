"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type Lane = { asset_class: string; instrument_type: string; enabled: boolean };
type Matrix = { account_id: string; version: number; lanes: Lane[] };
type BindingScope = "MARKET_RESEARCH" | "ECONOMIC_CONTEXT";

const marketCapabilities = ["DISCOVERY", "INSTRUMENT_DIRECTORY", "QUOTE", "CANDLES", "FUTURES_CHAIN", "CONTRACT_DETAILS", "OPEN_INTEREST"];
const economicCapabilities = ["ECONOMIC_CALENDAR", "MACROECONOMIC", "NEWS"];

export function ProviderBindings() {
  const client = useQueryClient();
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const [accountId, setAccountId] = useState("");
  const selectedAccountId = accountId || accounts.data?.find(item => item.state !== "DELETED")?.id || "";
  const matrix = useQuery<Matrix>({ queryKey: ["research", "matrix", selectedAccountId], queryFn: () => api(`/accounts/${selectedAccountId}/research-matrix`), enabled: Boolean(selectedAccountId) });
  const bindings = useQuery<Resource[]>({ queryKey: ["provider-bindings", selectedAccountId], queryFn: () => api(`/accounts/${selectedAccountId}/provider-bindings`), enabled: Boolean(selectedAccountId) });
  const enabledLanes = useMemo(() => (matrix.data?.lanes ?? []).filter(lane => lane.enabled), [matrix.data?.lanes]);
  const [scope, setScope] = useState<BindingScope>("MARKET_RESEARCH");
  const [lane, setLane] = useState("");
  const [capability, setCapability] = useState("DISCOVERY");
  const [connectionId, setConnectionId] = useState("");
  const [priority, setPriority] = useState("1");
  const [message, setMessage] = useState("");

  const selectedLane = enabledLanes.some(item => `${item.asset_class}:${item.instrument_type}` === lane)
    ? lane
    : enabledLanes[0] ? `${enabledLanes[0].asset_class}:${enabledLanes[0].instrument_type}` : "";

  const invalidate = async () => {
    await client.invalidateQueries({ queryKey: ["provider-bindings", selectedAccountId] });
    await client.invalidateQueries({ queryKey: ["configuration", "connections"] });
  };
  const create = useMutation({
    mutationFn: () => {
      const [asset_class, instrument_type] = selectedLane.split(":");
      return api(`/accounts/${selectedAccountId}/provider-bindings`, { method: "POST", body: JSON.stringify({ binding_scope: scope, ...(scope === "MARKET_RESEARCH" ? { lane: { asset_class, instrument_type } } : {}), capability, authority_purpose: scope === "MARKET_RESEARCH" ? "DISCOVERY" : "REFERENCE", connection_id: connectionId, priority: Number(priority) }) });
    },
    onSuccess: async () => { setMessage("Provider binding saved. Use Test & verify to confirm this exact authority."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const testAndVerify = useMutation({
    mutationFn: async (binding: Resource) => {
      await api(`/configuration/connections/${String(binding.connection_id)}/test`, { method: "POST" });
      return api(`/accounts/${selectedAccountId}/provider-bindings/${binding.id}/verify`, { method: "POST" });
    },
    onSuccess: async () => { setMessage("Connection tested and provider binding verified for the selected account."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const remove = useMutation({
    mutationFn: (binding: Resource) => api(`/accounts/${selectedAccountId}/provider-bindings/${binding.id}`, { method: "DELETE" }),
    onSuccess: async () => { setMessage("Provider binding removed. You can create its replacement above."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const activeAccounts = (accounts.data ?? []).filter(item => item.state !== "DELETED");
  const activeConnections = (connections.data ?? []).filter(item => item.state !== "DELETED");
  const connectionNames = new Map(activeConnections.map(item => [item.id, String(item.name)]));
  const choices = scope === "MARKET_RESEARCH" ? marketCapabilities : economicCapabilities;

  return <section className="section-stack">
    <header><p className="eyebrow">Connection authority</p><h2>Provider bindings</h2><p className="muted">Bind configured data sources to this account’s enabled market lanes or to its economic context. Market lanes always come from the active account research matrix.</p></header>
    {message ? <p className={create.isError || testAndVerify.isError || remove.isError ? "notice bad" : "notice good"}>{message}</p> : null}
    <article className="card form-stack">
      <label>Trading account<select value={selectedAccountId} onChange={event => { setAccountId(event.target.value); setLane(""); }}>{activeAccounts.map(account => <option key={account.id} value={account.id}>{String(account.name)}</option>)}</select></label>
      <div className="form-grid"><label>Binding use<select value={scope} onChange={event => { const nextScope = event.target.value as BindingScope; setScope(nextScope); setCapability(nextScope === "MARKET_RESEARCH" ? "DISCOVERY" : "ECONOMIC_CALENDAR"); }}><option value="MARKET_RESEARCH">Market research</option><option value="ECONOMIC_CONTEXT">Economic calendar, news & macro context</option></select></label>{scope === "MARKET_RESEARCH" ? <label>Matrix lane<select required value={selectedLane} onChange={event => setLane(event.target.value)}>{enabledLanes.map(item => <option key={`${item.asset_class}:${item.instrument_type}`} value={`${item.asset_class}:${item.instrument_type}`}>{item.asset_class} · {item.instrument_type}</option>)}</select></label> : <label>Coverage<output>Account economic context</output></label>}</div>
      {scope === "MARKET_RESEARCH" && enabledLanes.length === 0 ? <p className="notice bad">This account has no enabled research lanes. Update its matrix in Research first.</p> : null}
      <div className="form-grid"><label>Capability<select value={capability} onChange={event => setCapability(event.target.value)}>{choices.map(item => <option key={item}>{item}</option>)}</select></label><label>Priority<input type="number" min="1" value={priority} onChange={event => setPriority(event.target.value)} /></label></div>
      <label>Configured connection<select required value={connectionId} onChange={event => setConnectionId(event.target.value)}><option value="">Select a connection</option>{activeConnections.map(connection => <option key={connection.id} value={connection.id}>{String(connection.name)} · {String(connection.provider)} · {String(connection.health ?? "UNTESTED")}</option>)}</select></label>
      <button className="btn primary" disabled={!selectedAccountId || !connectionId || create.isPending || (scope === "MARKET_RESEARCH" && !selectedLane)} onClick={() => create.mutate()}>{create.isPending ? "Saving…" : "Save provider binding"}</button>
    </article>
    <article className="card"><h3>Current provider bindings</h3>{bindings.data?.length ? <div className="table-wrap"><table><thead><tr><th>Use</th><th>Coverage</th><th>Capability</th><th>Connection</th><th>Status</th><th /></tr></thead><tbody>{bindings.data.map(binding => { const bindingLane = binding.lane as Lane | undefined; return <tr key={binding.id}><td>{String(binding.binding_scope ?? "MARKET_RESEARCH").replaceAll("_", " ")}</td><td>{bindingLane ? `${bindingLane.asset_class} · ${bindingLane.instrument_type}` : "Economic context"}</td><td>{String(binding.capability)}</td><td>{connectionNames.get(String(binding.connection_id)) ?? String(binding.connection_id)}</td><td>{String(binding.verification_status)}</td><td><div className="actions">{binding.verification_status === "VERIFIED" ? <span>Verified</span> : <button className="btn compact" disabled={testAndVerify.isPending} onClick={() => testAndVerify.mutate(binding)}>Test & verify</button>}<button className="btn compact danger" disabled={remove.isPending} onClick={() => remove.mutate(binding)}>Remove</button></div></td></tr>; })}</tbody></table></div> : <p className="empty">No provider bindings for this account.</p>}</article>
  </section>;
}
