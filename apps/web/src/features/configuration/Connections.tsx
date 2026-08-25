"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MT5Connection } from "@/features/connections/MT5Connection";
import { api, type Resource } from "@/lib/api";

const providers = [
  { id: "TWELVE_DATA", label: "Twelve Data", credential: true, purpose: "market_data" },
  { id: "COINBASE", label: "Coinbase", credential: false, purpose: "market_data" },
  { id: "COINGECKO", label: "CoinGecko", credential: false, purpose: "discovery" },
  { id: "FRED", label: "FRED", credential: true, purpose: "macro" },
  { id: "CALENDAR", label: "Calendar", credential: false, purpose: "calendar" },
  { id: "NEWS", label: "News", credential: false, purpose: "news" },
  { id: "FOREX_FACTORY", label: "Forex Factory", credential: false, purpose: "news" },
  { id: "MT5_BRIDGE", label: "MT5 Bridge", credential: true, purpose: "broker" },
] as const;

type Provider = typeof providers[number]["id"];
type ForexFactoryEvent = { name: string; currency: string; impact: string; scheduled_at: string; source: string };
type ForexFactoryScrape = { connection_id: string; provider: string; feed_url: string; fetched_at: string; count: number; events: ForexFactoryEvent[] };

export function Connections() {
  const queryClient = useQueryClient();
  const credentials = useQuery<Resource[]>({ queryKey: ["configuration", "credentials"], queryFn: () => api("/configuration/credentials") });
  const connections = useQuery<Resource[]>({ queryKey: ["configuration", "connections"], queryFn: () => api("/configuration/connections") });
  const [credential, setCredential] = useState({ name: "", provider: "TWELVE_DATA" as Provider, purpose: "market_data", secret: "" });
  const [connection, setConnection] = useState({ name: "", provider: "TWELVE_DATA" as Provider, credential_id: "", bridge_url: "http://host.docker.internal:8765", account_reference: "", base_url: "", feed_url: "", test_symbol: "EUR/USD", forex_universe: "EUR/USD,GBP/USD,USD/JPY", metals_universe: "XAU/USD,XAG/USD", crypto_universe: "BTC-USD,ETH-USD,SOL-USD" });
  const [message, setMessage] = useState("");
  const [forexFactoryScrape, setForexFactoryScrape] = useState<ForexFactoryScrape | null>(null);
  const selectedProvider = providers.find(item => item.id === connection.provider) ?? providers[0];
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: ["configuration"] }); };
  const createCredential = useMutation({
    mutationFn: () => api("/configuration/credentials", { method: "POST", body: JSON.stringify(credential) }),
    onSuccess: async () => { setCredential({ ...credential, name: "", secret: "" }); setMessage("Encrypted credential saved. Select it when creating the connection."); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const createConnection = useMutation({
    mutationFn: () => {
      const configuration: Record<string, string> = {};
      if (connection.provider === "TWELVE_DATA") Object.assign(configuration, { test_symbol: connection.test_symbol, forex_universe: connection.forex_universe, metals_universe: connection.metals_universe });
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
  const testCredential = useMutation({
    mutationFn: (id: string) => api<Resource>(`/configuration/credentials/${id}/test`, { method: "POST" }),
    onSuccess: async item => { setMessage(`${String(item.name)} credential is ${String(item.status)}.`); await invalidate(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const scrapeForexFactory = useMutation({
    mutationFn: (id: string) => api<ForexFactoryScrape>(`/configuration/connections/${id}/forex-factory/scrape`, { method: "POST" }),
    onSuccess: result => { setForexFactoryScrape(result); setMessage(`Forex Factory scraper fetched ${result.count} events.`); },
    onError: (error: Error) => setMessage(error.message),
  });
  const mt5Connections = useMemo(() => (connections.data ?? []).filter(item => item.provider === "MT5_BRIDGE"), [connections.data]);
  const dataConnections = useMemo(() => (connections.data ?? []).filter(item => item.provider !== "MT5_BRIDGE"), [connections.data]);
  const forexFactoryConnections = useMemo(() => (connections.data ?? []).filter(item => item.provider === "FOREX_FACTORY"), [connections.data]);
  const submitCredential = (event: FormEvent) => { event.preventDefault(); setMessage(""); createCredential.mutate(); };
  const submitConnection = (event: FormEvent) => { event.preventDefault(); setMessage(""); createConnection.mutate(); };

  return <section className="section-stack">
    <header><p className="eyebrow">Provider boundary</p><h1>Connections & data sources</h1><p className="muted">Configure the authoritative sources used by research, backtesting, macro context, and read-only broker reconciliation. Secrets remain encrypted and replacement requires MFA step-up.</p></header>
    <MT5Connection connections={mt5Connections} onTest={id => testConnection.mutate(id)} testing={testConnection.isPending} />
    <div className="grid two">
      <form className="card form-stack" onSubmit={submitCredential}><h2>1. Store a credential</h2><label>Provider<select value={credential.provider} onChange={event => { const provider = providers.find(item => item.id === event.target.value)!; setCredential({ ...credential, provider: provider.id, purpose: provider.purpose }); }}>
        {providers.filter(item => item.credential).map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label><label>Credential name<input required value={credential.name} onChange={event => setCredential({ ...credential, name: event.target.value })} /></label><label>Secret / API key<input required type="password" value={credential.secret} onChange={event => setCredential({ ...credential, secret: event.target.value })} /></label><button className="btn primary" disabled={createCredential.isPending}>Encrypt credential</button></form>
      <form className="card form-stack" onSubmit={submitConnection}><h2>2. Add connection</h2><label>Data source<select value={connection.provider} onChange={event => setConnection({ ...connection, provider: event.target.value as Provider, credential_id: "" })}>{providers.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label>Connection name<input required value={connection.name} onChange={event => setConnection({ ...connection, name: event.target.value })} /></label>
        {selectedProvider.credential ? <label>Encrypted credential<select required value={connection.credential_id} onChange={event => setConnection({ ...connection, credential_id: event.target.value })}><option value="">Select credential</option>{credentials.data?.filter(item => item.provider === connection.provider).map(item => <option key={item.id} value={item.id}>{String(item.name)} · {String(item.masked_suffix)}</option>)}</select></label> : <p className="muted">This source uses public read endpoints and needs no secret.</p>}
        {connection.provider === "TWELVE_DATA" ? <><label>Test symbol<input value={connection.test_symbol} onChange={event => setConnection({ ...connection, test_symbol: event.target.value })} /></label><label>Forex universe<input value={connection.forex_universe} onChange={event => setConnection({ ...connection, forex_universe: event.target.value })} /></label><label>Metals universe<input value={connection.metals_universe} onChange={event => setConnection({ ...connection, metals_universe: event.target.value })} /></label></> : null}
        {connection.provider === "COINBASE" ? <label>Crypto universe<input value={connection.crypto_universe} onChange={event => setConnection({ ...connection, crypto_universe: event.target.value })} /></label> : null}
        {["CALENDAR", "NEWS"].includes(connection.provider) ? <label>Provider base URL<input required type="url" placeholder="https://provider.example" value={connection.base_url} onChange={event => setConnection({ ...connection, base_url: event.target.value })} /></label> : null}
        {connection.provider === "FOREX_FACTORY" ? <label>Optional feed URL<input type="url" placeholder="Uses the maintained Forex Factory calendar feed by default" value={connection.feed_url} onChange={event => setConnection({ ...connection, feed_url: event.target.value })} /></label> : null}
        {connection.provider === "MT5_BRIDGE" ? <><label>Bridge URL<input required value={connection.bridge_url} onChange={event => setConnection({ ...connection, bridge_url: event.target.value })} /></label><label>Account reference<input required value={connection.account_reference} onChange={event => setConnection({ ...connection, account_reference: event.target.value })} /></label></> : null}
        <button className="btn primary" disabled={createConnection.isPending}>Save connection</button>
      </form>
    </div>
    {message && <p className="notice">{message}</p>}
    <article className="card"><h2>News data source</h2><p className="muted">Matrades uses the configured Forex Factory calendar scraper for scheduled macro/news context. If it is not configured, no news facts are fabricated; a custom News connection can be used explicitly instead.</p>{(() => { const source = connections.data?.find(item => item.provider === "FOREX_FACTORY") ?? connections.data?.find(item => item.provider === "NEWS"); return source ? <p className="notice good">Active news source: {source.provider === "FOREX_FACTORY" ? "Forex Factory scraper" : String(source.name)} · {String(source.health)}</p> : <p className="notice warn">No news source configured.</p>; })()}</article>
    <article className="card"><div className="split"><div><h2>Forex Factory scraper</h2><p className="muted">Run the calendar scraper directly to retrieve normalized scheduled events. Autonomous research cycles also run this fetch and archive the result with the cycle.</p></div>{forexFactoryConnections.length ? <div className="actions">{forexFactoryConnections.map(item => <button className="btn primary" key={item.id} disabled={scrapeForexFactory.isPending} onClick={() => scrapeForexFactory.mutate(item.id)}>{scrapeForexFactory.isPending ? "Scraping…" : `Scrape ${String(item.name)}`}</button>)}</div> : null}</div>{forexFactoryConnections.length ? forexFactoryScrape ? <><p className="notice good">Fetched {forexFactoryScrape.count} events at {new Date(forexFactoryScrape.fetched_at).toLocaleString()}.</p>{forexFactoryScrape.events.length ? <div className="table-wrap"><table><thead><tr><th>Scheduled</th><th>Currency</th><th>Impact</th><th>Event</th></tr></thead><tbody>{forexFactoryScrape.events.slice(0, 100).map((event, index) => <tr key={`${event.scheduled_at}-${event.currency}-${index}`}><td>{new Date(event.scheduled_at).toLocaleString()}</td><td>{event.currency}</td><td>{event.impact}</td><td>{event.name}</td></tr>)}</tbody></table>{forexFactoryScrape.count > 100 ? <p className="muted">Showing the first 100 of {forexFactoryScrape.count} events.</p> : null}</div> : <p className="empty">The feed returned no normalized events.</p>}</> : <p className="empty">Choose Forex Factory above and save a connection, then run the scraper here.</p> : <p className="empty">No Forex Factory scraper configured.</p>}</article>
    <article className="card"><h2>Stored credentials</h2><p className="muted">Secrets remain •••• masked after entry. Testing a connection also updates its linked credential status.</p>{credentials.data?.length ? <ul className="record-list">{credentials.data.map(item => <li key={item.id}><strong>{String(item.name)}</strong><span>{String(item.provider)} · {String(item.masked_suffix)}</span><small>{String(item.status)}{item.last_tested ? ` · tested ${new Date(String(item.last_tested)).toLocaleString()}` : ""}</small><button className="btn compact" disabled={testCredential.isPending} onClick={() => testCredential.mutate(item.id)}>Test credential</button></li>)}</ul> : <p className="empty">No encrypted provider credentials yet.</p>}</article>
    <article className="card"><h2>Configured data sources</h2><p className="muted">Twelve Data health checks are cached for one hour to conserve API quota. Replacing its credential resets the cache and allows an immediate fresh check.</p>{connections.isPending ? <p>Loading…</p> : dataConnections.length ? <div className="table-wrap"><table><thead><tr><th>Name</th><th>Source</th><th>Health</th><th>Last checked</th><th>Capabilities</th><th /></tr></thead><tbody>{dataConnections.map(item => <tr key={item.id}><td>{String(item.name)}</td><td>{providers.find(provider => provider.id === item.provider)?.label ?? String(item.provider)}</td><td><span className={`status ${String(item.health).toLowerCase()}`}>{String(item.health)}</span>{item.last_error ? <small className="muted">{String(item.last_error)}</small> : null}</td><td>{item.last_checked ? new Date(String(item.last_checked)).toLocaleString() : "Never"}{item.health_cached ? " (cached)" : ""}</td><td>{((item.capabilities as string[]) ?? []).join(", ") || "Not tested"}</td><td><button className="btn compact" disabled={testConnection.isPending} onClick={() => testConnection.mutate(item.id)}>Test</button></td></tr>)}</tbody></table></div> : <p className="empty">No data-source connections configured.</p>}</article>
  </section>;
}
