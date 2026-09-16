"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource, withStepUp } from "@/lib/api";
import { MfaDeleteDialog } from "@/components/MfaDeleteDialog";

const providers = [
  { id: "TWELVE_DATA", label: "Twelve Data", credential: true, purpose: "market_data" },
  { id: "COINBASE", label: "Coinbase", credential: false, purpose: "market_data" },
  { id: "COINGECKO", label: "CoinGecko", credential: false, purpose: "discovery" },
  { id: "FRED", label: "FRED", credential: true, purpose: "macro" },
  { id: "CFTC", label: "CFTC Commitments of Traders", credential: false, purpose: "positioning" },
  { id: "FUTURES_REFERENCE", label: "Futures reference / contract chain", credential: false, purpose: "market_data" },
  { id: "CALENDAR", label: "Calendar", credential: false, purpose: "calendar" },
  { id: "NEWS", label: "News", credential: false, purpose: "news" },
  { id: "FOREX_FACTORY", label: "Forex Factory", credential: false, purpose: "news" },
  { id: "SERPAPI", label: "SerpApi + YouTube transcript ingestion", credential: true, purpose: "knowledge" },
  { id: "OPENAI", label: "OpenAI", credential: true, purpose: "knowledge_embedding" },
  { id: "COHERE", label: "Cohere Rerank", credential: true, purpose: "knowledge_reranking" },
  { id: "MT5_BRIDGE", label: "MT5 Bridge", credential: true, purpose: "broker" },
] as const;

type Provider = typeof providers[number]["id"];
type CredentialReplacement = { id: string; name: string; provider: Provider; purpose: string; secret: string };
type AccountSchedule = { account_id: string; enabled: boolean; run_at: string; timezone: string; weekdays: number[]; next_run_at: string | null; configured: boolean; saved_at: string | null };
type ForexFactoryEvent = { name: string; currency: string; impact: string; scheduled_at: string; source: string };
type ForexFactoryScrape = { connection_id: string; provider: string; feed_url: string; fetched_at: string; count: number; events: ForexFactoryEvent[]; period_key: string; period_start: string; period_end: string; archive_path: string; skipped: boolean; message: string };

function generateBridgeSecret() {
  return Array.from(crypto.getRandomValues(new Uint8Array(32)), value => value.toString(16).padStart(2, "0")).join("");
}

export function Connections() {
  const queryClient = useQueryClient();
  const credentials = useQuery<Resource[]>({ queryKey: ["configuration", "credentials"], queryFn: () => api("/configuration/credentials") });
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const [credential, setCredential] = useState({ name: "", provider: "TWELVE_DATA" as Provider, purpose: "market_data", secret: "" });
  const [replacement, setReplacement] = useState<CredentialReplacement | null>(null);
  const [replacementMfaPending, setReplacementMfaPending] = useState(false);
  const [credentialRemovalTarget, setCredentialRemovalTarget] = useState<Resource | null>(null);
  const [connection, setConnection] = useState({ name: "", provider: "TWELVE_DATA" as Provider, credential_id: "", bridge_url: "http://host.docker.internal:8765", account_reference: "", base_url: "", feed_url: "", crypto_universe: "BTC-USD,ETH-USD,SOL-USD" });
  const [message, setMessage] = useState("");
  const [removalTarget, setRemovalTarget] = useState<Resource | null>(null);
  const [forexFactoryScrape, setForexFactoryScrape] = useState<ForexFactoryScrape | null>(null);
  const [scraperAccountId, setScraperAccountId] = useState("");
  const [scraperScheduleDraft, setScraperScheduleDraft] = useState<AccountSchedule | null>(null);
  const [scraperScheduleEditing, setScraperScheduleEditing] = useState(false);
  const selectedProvider = providers.find(item => item.id === connection.provider) ?? providers[0];
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: ["configuration"] }); };
  const createCredential = useMutation({
    mutationFn: () => api("/configuration/credentials", { method: "POST", body: JSON.stringify(credential) }),
    onSuccess: async () => { const mt5 = credential.provider === "MT5_BRIDGE"; setCredential({ ...credential, name: "", secret: "" }); setMessage(mt5 ? "Authoritative MT5 bridge secret saved. Use the same value for InpBridgeSecret in the EA, then select this credential for the connection." : "Encrypted credential saved. Select it when creating the connection."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const createConnection = useMutation({
    mutationFn: () => {
      const configuration: Record<string, string> = {};
      if (connection.provider === "COINBASE") Object.assign(configuration, { crypto_universe: connection.crypto_universe });
      if (["CALENDAR", "NEWS"].includes(connection.provider)) Object.assign(configuration, { base_url: connection.base_url });
      if (connection.provider === "FOREX_FACTORY" && connection.feed_url) Object.assign(configuration, { feed_url: connection.feed_url });
      if (connection.provider === "MT5_BRIDGE") Object.assign(configuration, { bridge_url: connection.bridge_url, account_reference: connection.account_reference });
      return api("/configuration/connections", { method: "POST", body: JSON.stringify({ name: connection.name, provider: connection.provider, credential_id: connection.credential_id || null, configuration, active: true }) });
    },
    onSuccess: async () => { setConnection({ ...connection, name: "" }); setMessage("Connection saved. Run Test to record live provider health."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const testConnection = useMutation({
    mutationFn: (id: string) => api<Resource>(`/configuration/connections/${id}/test`, { method: "POST" }),
    onSuccess: async item => { setMessage(`${String(item.name)} is ${String(item.health)}${item.health_cached ? " (cached; Twelve Data checks run at most once per hour)" : ""}${item.last_error ? ` · ${String(item.last_error)}` : ""}.`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const stepUpAndRemove = useMutation({
    mutationFn: async (code: string) => {
      if (!removalTarget) throw new Error("Choose a data source to remove");
      return withStepUp("connection.change", code, grant => api<Resource>(`/configuration/connections/${removalTarget.id}`, {
        method: "DELETE",
        headers: { "Step-Up-Grant": grant },
      }));
    },
    onSuccess: async item => {
      setRemovalTarget(null);
      setMessage(`${String(item.name)} removed from active data sources; its audit history is retained.`);
      await invalidate();
    },
    onError: (error: Error) => setMessage(error.message),
  });
  const testCredential = useMutation({
    mutationFn: (id: string) => api<Resource>(`/configuration/credentials/${id}/test`, { method: "POST" }),
    onSuccess: async item => { setMessage(`${String(item.name)} credential is ${String(item.status)}.`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const replaceCredential = useMutation({
    mutationFn: ({ input, code }: { input: CredentialReplacement; code: string }) => withStepUp("credential.change", code, grant => api<Resource>(`/configuration/credentials/${input.id}`, { method: "PATCH", headers: { "Step-Up-Grant": grant }, body: JSON.stringify({ name: input.name, provider: input.provider, purpose: input.purpose, secret: input.secret }) })),
    onSuccess: async item => { setReplacement(null); setReplacementMfaPending(false); setMessage(`${String(item.name)} replaced. Test the linked connection for a fresh provider check.`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const removeCredential = useMutation({
    mutationFn: ({ credential: target, code }: { credential: Resource; code: string }) => withStepUp("credential.change", code, grant => api<Resource & { disabled_connection_count?: number }>(`/configuration/credentials/${target.id}`, { method: "DELETE", headers: { "Step-Up-Grant": grant } })),
    onSuccess: async item => { setCredentialRemovalTarget(null); setMessage(`${String(item.name)} secret deleted.${item.disabled_connection_count ? ` ${String(item.disabled_connection_count)} linked connection(s) were disabled.` : ""}`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const scrapeForexFactory = useMutation({
    mutationFn: (id: string) => api<ForexFactoryScrape>(`/configuration/connections/${id}/forex-factory/scrape`, { method: "POST" }),
    onSuccess: async result => { setForexFactoryScrape(result); setMessage(result.skipped ? result.message : `Forex Factory scraper fetched and archived ${result.count} events for ${result.period_key}.`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const dataConnections = useMemo(() => (connections.data ?? []).filter(item => item.state !== "DELETED"), [connections.data]);
  const forexFactoryConnections = useMemo(() => (connections.data ?? []).filter(item => item.provider === "FOREX_FACTORY"), [connections.data]);
  const selectedScraperAccountId = scraperAccountId || accounts.data?.[0]?.id || "";
  const scraperSchedule = useQuery<AccountSchedule>({ queryKey: ["configuration", "account", selectedScraperAccountId, "forex-factory-schedule"], queryFn: () => api(`/configuration/accounts/${selectedScraperAccountId}/forex-factory-schedule`), enabled: Boolean(selectedScraperAccountId) });
  const editableScraperSchedule = scraperScheduleDraft?.account_id === selectedScraperAccountId ? scraperScheduleDraft : scraperSchedule.data;
  const submitCredential = (event: FormEvent) => { event.preventDefault(); setMessage(""); createCredential.mutate(); };
  const submitConnection = (event: FormEvent) => { event.preventDefault(); setMessage(""); createConnection.mutate(); };
  const saveScraperSchedule = useMutation({
    mutationFn: () => {
      if (!editableScraperSchedule) throw new Error("Select a trading account first");
      const { enabled, run_at, timezone, weekdays } = editableScraperSchedule;
      return api<AccountSchedule>(`/configuration/accounts/${selectedScraperAccountId}/forex-factory-schedule`, { method: "PUT", body: JSON.stringify({ enabled, run_at, timezone, weekdays }) });
    },
    onSuccess: async result => { setScraperScheduleDraft(result); setScraperScheduleEditing(false); setMessage("Forex Factory scraper schedule saved for this trading account."); await queryClient.invalidateQueries({ queryKey: ["configuration", "account", selectedScraperAccountId, "forex-factory-schedule"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const removeScraperSchedule = useMutation({
    mutationFn: () => api<AccountSchedule>(`/configuration/accounts/${selectedScraperAccountId}/forex-factory-schedule`, { method: "DELETE" }),
    onSuccess: async result => { setScraperScheduleDraft(result); setScraperScheduleEditing(false); setMessage("Forex Factory scraper schedule removed. Automatic scraping is disabled for this account."); await queryClient.invalidateQueries({ queryKey: ["configuration", "account", selectedScraperAccountId, "forex-factory-schedule"] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const changeScraperSchedule = (patch: Partial<AccountSchedule>) => { if (editableScraperSchedule) setScraperScheduleDraft({ ...editableScraperSchedule, ...patch }); };

  return <section className="section-stack">
    <header><p className="eyebrow">Provider boundary</p><h1>Connections & data sources</h1><p className="muted">Configure the authoritative sources used by research, backtesting, macro context, and read-only broker reconciliation. Secrets remain encrypted and replacement requires MFA step-up.</p></header>
    <div className="grid two">
      <form className="card form-stack" onSubmit={submitCredential}><h2>1. Store a credential</h2><label>Provider<select value={credential.provider} onChange={event => { const provider = providers.find(item => item.id === event.target.value)!; setCredential({ ...credential, provider: provider.id, purpose: provider.purpose }); }}>
        {providers.filter(item => item.credential).map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label><label>Credential name<input required value={credential.name} onChange={event => setCredential({ ...credential, name: event.target.value })} /></label><label>{credential.provider === "MT5_BRIDGE" ? "Authoritative bridge secret" : "Secret / API key"}<input required type="password" value={credential.secret} onChange={event => setCredential({ ...credential, secret: event.target.value })} /></label>{credential.provider === "MT5_BRIDGE" ? <><div className="actions"><button type="button" className="btn compact" onClick={() => setCredential({ ...credential, secret: generateBridgeSecret() })}>Generate secure secret</button><button type="button" className="btn compact" disabled={!credential.secret} onClick={async () => { await navigator.clipboard.writeText(credential.secret); setMessage("Bridge secret copied. Paste it into the EA InpBridgeSecret input before leaving this page."); }}>Copy for EA</button></div><p className="muted">The encrypted value saved here is the source of truth used by the bridge. Copy the same value into <code>InpBridgeSecret</code> in the EA. It cannot be displayed again after saving.</p></> : null}<button className="btn primary" disabled={createCredential.isPending}>Encrypt credential</button></form>
      <form className="card form-stack" onSubmit={submitConnection}><h2>2. Add connection</h2><label>Data source<select value={connection.provider} onChange={event => setConnection({ ...connection, provider: event.target.value as Provider, credential_id: "" })}>{providers.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label>Connection name<input required value={connection.name} onChange={event => setConnection({ ...connection, name: event.target.value })} /></label>
        {selectedProvider.credential ? <label>Encrypted credential<select required value={connection.credential_id} onChange={event => setConnection({ ...connection, credential_id: event.target.value })}><option value="">Select credential</option>{credentials.data?.filter(item => item.provider === connection.provider).map(item => <option key={item.id} value={item.id}>{String(item.name)} · {String(item.masked_suffix)}</option>)}</select></label> : <p className="muted">This source uses public read endpoints and needs no secret.</p>}
        {connection.provider === "TWELVE_DATA" ? <p className="muted">Connection testing validates the API key only and does not require a pair. Autonomous market research discovers and approves the instrument; only that selected pair is then requested from Twelve Data. Discovery universes are managed by the server configuration.</p> : null}
        {connection.provider === "COHERE" ? <p className="muted">Testing makes a small, billable rerank request with synthetic text. After saving this connection, enable it under Knowledge → Cohere knowledge reranking. Queries and authorized candidate chunks are sent to Cohere only when reranking is enabled.</p> : null}
        {connection.provider === "COINBASE" ? <label>Crypto universe<input value={connection.crypto_universe} onChange={event => setConnection({ ...connection, crypto_universe: event.target.value })} /></label> : null}
        {["CALENDAR", "NEWS"].includes(connection.provider) ? <label>Provider base URL<input required type="url" placeholder="https://provider.example" value={connection.base_url} onChange={event => setConnection({ ...connection, base_url: event.target.value })} /></label> : null}
        {connection.provider === "FOREX_FACTORY" ? <label>Optional feed URL<input type="url" placeholder="Uses the maintained Forex Factory calendar feed by default" value={connection.feed_url} onChange={event => setConnection({ ...connection, feed_url: event.target.value })} /></label> : null}
        {connection.provider === "MT5_BRIDGE" ? <><label>Bridge URL<input required value={connection.bridge_url} onChange={event => setConnection({ ...connection, bridge_url: event.target.value })} /></label><label>Account reference<input required value={connection.account_reference} onChange={event => setConnection({ ...connection, account_reference: event.target.value })} /></label></> : null}
        <button className="btn primary" disabled={createConnection.isPending}>Save connection</button>
      </form>
    </div>
    {message && <p className="notice">{message}</p>}
    <article className="card form-stack"><h2>Forex Factory scraper schedule</h2><p className="muted">The scheduler checks every minute and runs the scraper independently for each trading account. A period already archived is skipped without another provider request.</p>{accounts.data?.length ? <><label>Trading account<select value={selectedScraperAccountId} onChange={event => { setScraperAccountId(event.target.value); setScraperScheduleDraft(null); setScraperScheduleEditing(false); }}><option value="">Select an account</option>{accounts.data.map(account => <option key={account.id} value={account.id}>{String(account.name)}</option>)}</select></label>{editableScraperSchedule?.configured && !scraperScheduleEditing ? <div className="inset form-stack"><strong>Saved scraper schedule</strong><span>{editableScraperSchedule.enabled ? `${editableScraperSchedule.run_at} · ${editableScraperSchedule.timezone}` : "Disabled"}</span><small>Next run: {editableScraperSchedule.next_run_at ? new Date(editableScraperSchedule.next_run_at).toLocaleString() : "Schedule disabled"}{editableScraperSchedule.saved_at ? ` · last saved ${new Date(editableScraperSchedule.saved_at).toLocaleString()}` : ""}</small><div className="actions"><button className="btn" onClick={() => setScraperScheduleEditing(true)}>Edit / replace schedule</button><button className="btn danger" disabled={removeScraperSchedule.isPending} onClick={() => removeScraperSchedule.mutate()}>{removeScraperSchedule.isPending ? "Removing…" : "Remove schedule"}</button></div></div> : editableScraperSchedule ? <><div className="form-grid"><label>Run time<input type="time" value={editableScraperSchedule.run_at} onChange={event => changeScraperSchedule({ run_at: event.target.value })} /></label><label>Timezone<input value={editableScraperSchedule.timezone} placeholder="Africa/Kigali" onChange={event => changeScraperSchedule({ timezone: event.target.value })} /></label></div><label><input type="checkbox" checked={editableScraperSchedule.enabled} onChange={event => changeScraperSchedule({ enabled: event.target.checked })} /> Enable scheduled scraper</label><fieldset><legend>Run on</legend><div className="actions">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input type="checkbox" checked={editableScraperSchedule.weekdays.includes(index)} onChange={event => changeScraperSchedule({ weekdays: event.target.checked ? [...new Set([...editableScraperSchedule.weekdays, index])].sort() : editableScraperSchedule.weekdays.filter(item => item !== index) })} /> {day}</label>)}</div></fieldset><div className="actions"><button className="btn primary" disabled={saveScraperSchedule.isPending || (editableScraperSchedule.enabled && editableScraperSchedule.weekdays.length === 0)} onClick={() => saveScraperSchedule.mutate()}>{saveScraperSchedule.isPending ? "Saving…" : editableScraperSchedule.configured ? "Replace scraper schedule" : "Save new scraper schedule"}</button>{editableScraperSchedule.configured ? <button className="btn" onClick={() => { setScraperScheduleDraft(null); setScraperScheduleEditing(false); }}>Cancel</button> : null}</div></> : <p className="empty">Select an account to configure its scraper schedule.</p>}</> : <p className="empty">Configure a trading account first.</p>}</article>
    <article className="card"><div className="split"><div><h2>Forex Factory scraper</h2><p className="muted">Run the calendar scraper directly to retrieve normalized scheduled events. Autonomous scheduled runs use the same period archive and skip periods already saved.</p></div>{forexFactoryConnections.length ? <div className="actions">{forexFactoryConnections.map(item => <button className="btn primary" key={item.id} disabled={scrapeForexFactory.isPending} onClick={() => scrapeForexFactory.mutate(item.id)}>{scrapeForexFactory.isPending ? "Scraping…" : `Scrape ${String(item.name)}`}</button>)}</div> : null}</div>{forexFactoryConnections.length ? forexFactoryScrape ? <><p className={`notice ${forexFactoryScrape.skipped ? "warn" : "good"}`}>{forexFactoryScrape.message} Period: {forexFactoryScrape.period_start} → {forexFactoryScrape.period_end}. Archive: {forexFactoryScrape.archive_path}</p>{forexFactoryScrape.events.length ? <div className="table-wrap"><table><thead><tr><th>Scheduled</th><th>Currency</th><th>Impact</th><th>Event</th></tr></thead><tbody>{forexFactoryScrape.events.slice(0, 100).map((event, index) => <tr key={`${event.scheduled_at}-${event.currency}-${index}`}><td>{new Date(event.scheduled_at).toLocaleString()}</td><td>{event.currency}</td><td>{event.impact}</td><td>{event.name}</td></tr>)}</tbody></table>{forexFactoryScrape.count > 100 ? <p className="muted">Showing the first 100 of {forexFactoryScrape.count} events.</p> : null}</div> : <p className="empty">The feed returned no normalized events.</p>}</> : <p className="empty">Choose Forex Factory above and save a connection, then run the scraper here.</p> : <p className="empty">No Forex Factory scraper configured.</p>}</article>
    <article className="card"><h2>Stored credentials</h2><p className="muted">Secrets remain •••• masked after entry. Testing a connection also updates its linked credential status. Replacing a key keeps linked connections; deleting a key permanently discards its encrypted secret and disables linked connections.</p>{credentials.data?.length ? <ul className="record-list">{credentials.data.map(item => <li key={item.id}><strong>{String(item.name)}</strong><span>{String(item.provider)} · {String(item.masked_suffix)}</span><small>{String(item.status)}{item.last_tested ? ` · tested ${new Date(String(item.last_tested)).toLocaleString()}` : ""}</small><div className="actions"><button className="btn compact" disabled={testCredential.isPending} onClick={() => testCredential.mutate(item.id)}>Test credential</button><button className="btn compact" onClick={() => { setReplacementMfaPending(false); setReplacement({ id: item.id, name: String(item.name), provider: item.provider as Provider, purpose: String(item.purpose ?? "market_data"), secret: "" }); }}>Replace</button><button className="btn compact" disabled={removeCredential.isPending} onClick={() => setCredentialRemovalTarget(item)}>Delete</button></div></li>)}</ul> : <p className="empty">No encrypted provider credentials yet.</p>}{replacement ? <form className="form-stack inset" onSubmit={event => { event.preventDefault(); if (replacement.secret) setReplacementMfaPending(true); }}><h3>Replace {replacement.provider} credential</h3><label>Credential name<input required value={replacement.name} onChange={event => setReplacement({ ...replacement, name: event.target.value })} /></label><label>New secret / API key<input required type="password" value={replacement.secret} onChange={event => setReplacement({ ...replacement, secret: event.target.value })} /></label>{replacement.provider === "MT5_BRIDGE" ? <p className="muted">Replacing this authoritative secret immediately invalidates the old EA secret. Copy the new value into <code>InpBridgeSecret</code> after MFA verification.</p> : null}<div className="actions"><button className="btn primary" disabled={replaceCredential.isPending || !replacement.secret}>Continue to MFA verification</button><button type="button" className="btn" onClick={() => { setReplacementMfaPending(false); setReplacement(null); }}>Cancel</button></div><p className="muted">MFA verification is required before the current encrypted secret is replaced.</p></form> : null}</article>
    <article className="card"><h2>Configured data sources</h2><p className="muted">This includes market, economic, knowledge, and broker connections such as MT5 Bridge. Twelve Data health checks are cached for one hour to conserve API quota. Replacing its credential resets the cache and allows an immediate fresh check. Removing a source opens an MFA confirmation dialog.</p>{connections.isPending ? <p>Loading…</p> : dataConnections.length ? <div className="table-wrap"><table><thead><tr><th>Name</th><th>Source</th><th>Health</th><th>Last checked</th><th>Capabilities</th><th /></tr></thead><tbody>{dataConnections.map(item => <tr key={item.id}><td>{String(item.name)}</td><td>{providers.find(provider => provider.id === item.provider)?.label ?? String(item.provider)}</td><td><span className={`status ${String(item.health).toLowerCase()}`}>{String(item.health)}</span>{item.last_error ? <small className="muted">{String(item.last_error)}</small> : null}</td><td>{item.last_checked ? new Date(String(item.last_checked)).toLocaleString() : "Never"}{item.health_cached ? " (cached)" : ""}</td><td>{((item.capabilities as string[]) ?? []).join(", ") || "Not tested"}</td><td><div className="actions"><button className="btn compact" disabled={testConnection.isPending} onClick={() => testConnection.mutate(item.id)}>Test</button><button className="btn compact" disabled={stepUpAndRemove.isPending} onClick={() => { setRemovalTarget(item); setMessage(""); }}>Remove</button></div></td></tr>)}</tbody></table></div> : <p className="empty">No data-source connections configured.</p>}</article>
    {removalTarget ? <MfaDeleteDialog key={removalTarget.id} targetLabel={String(removalTarget.name)} scope="connection.change" busy={stepUpAndRemove.isPending} error={stepUpAndRemove.error instanceof Error ? stepUpAndRemove.error.message : undefined} onCancel={() => setRemovalTarget(null)} onConfirm={code => stepUpAndRemove.mutate(code)} /> : null}
    {replacement && replacementMfaPending ? <MfaDeleteDialog key={`replace-${replacement.id}`} targetLabel={replacement.name} scope="credential.change" title="Confirm credential replacement" description={<>Replace the encrypted secret for <strong>{replacement.name}</strong>? The previous secret will be permanently discarded.</>} confirmLabel="Verify and replace" busy={replaceCredential.isPending} error={replaceCredential.error instanceof Error ? replaceCredential.error.message : undefined} onCancel={() => setReplacementMfaPending(false)} onConfirm={code => replaceCredential.mutate({ input: replacement, code })} /> : null}
    {credentialRemovalTarget ? <MfaDeleteDialog key={credentialRemovalTarget.id} targetLabel={String(credentialRemovalTarget.name)} scope="credential.change" busy={removeCredential.isPending} error={removeCredential.error instanceof Error ? removeCredential.error.message : undefined} description={<>Permanently delete the encrypted secret for <strong>{String(credentialRemovalTarget.name)}</strong>? Any linked connections will be disabled.</>} onCancel={() => setCredentialRemovalTarget(null)} onConfirm={code => removeCredential.mutate({ credential: credentialRemovalTarget, code })} /> : null}
  </section>;
}
