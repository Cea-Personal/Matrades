"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";
import { OverviewIcon, type OverviewIconName } from "./OverviewIcon";

type Health = { state: string; components: { component: string; state: string }[] };
type Operations = { trade_plans: Resource[]; execution_commands: Resource[]; active_trades: Resource[]; execution_mode: string };
type EquityPoint = { id: string; observed_at: string; equity: string; balance: string };
type EquityHistory = { account_id: string; currency: string; points: EquityPoint[] };
type Limits = { effective: Record<string, { value: string; unit: string }> };
type Lane = { status: string; candidate?: { score: number; listing: { id: string; symbol: string; asset_class: string }; lane?: { asset_class: string } } };

function money(value: unknown, currency: string) {
  if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
  try { return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value)); }
  catch { return `${Number(value).toLocaleString("en-US")} ${currency}`; }
}

function relativeTime(value: string, now: Date | null) {
  if (!now || !Number.isFinite(Date.parse(value))) return "—";
  const minutes = Math.max(0, Math.floor((now.getTime() - Date.parse(value)) / 60_000));
  return minutes < 1 ? "Just now" : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`;
}

function EquityChart({ points, currency }: { points: EquityPoint[]; currency: string }) {
  const gradient = useId();
  const [hover, setHover] = useState<number | null>(null);
  const values = points.flatMap(point => [Number(point.equity), Number(point.balance)]);
  const low = Math.min(...values), high = Math.max(...values);
  const padding = Math.max((high - low) * .16, Math.abs(high) * .005, 1);
  const bottom = low - padding, top = high + padding;
  const start = Date.parse(points[0].observed_at);
  const duration = Date.parse(points.at(-1)!.observed_at) - start;
  const x = (index: number) => 44 + (duration > 0 ? (Date.parse(points[index].observed_at) - start) / duration : index / (points.length - 1)) * 324;
  const y = (value: number) => 14 + (top - value) / (top - bottom) * 122;
  const line = (field: "equity" | "balance") => points.map((point, index) => `${index ? "L" : "M"}${x(index)},${y(Number(point[field]))}`).join(" ");
  const active = hover === null ? null : points[Math.min(hover, points.length - 1)];
  return <div className="equity-chart">
    <svg viewBox="0 0 380 162" role="img" aria-label="Recorded account equity and balance history" onMouseLeave={() => setHover(null)} onMouseMove={event => {
      const rect = event.currentTarget.getBoundingClientRect();
      const position = (event.clientX - rect.left) / rect.width * 380;
      setHover(points.reduce((closest, _, index) => Math.abs(x(index) - position) < Math.abs(x(closest) - position) ? index : closest, 0));
    }}>
      <defs><linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#00d9a6" stopOpacity=".23" /><stop offset="100%" stopColor="#00d9a6" stopOpacity="0" /></linearGradient></defs>
      {[0, 1, 2, 3].map(index => {
        const value = top - (top - bottom) * index / 3;
        return <g key={index}><line x1="44" x2="368" y1={y(value)} y2={y(value)} className="chart-grid" /><text x="36" y={y(value) + 4} textAnchor="end">{new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value)}</text></g>;
      })}
      <path d={`${line("equity")} L368,136 L44,136 Z`} fill={`url(#${gradient})`} />
      <path d={line("balance")} className="chart-balance" />
      <path d={line("equity")} className="chart-equity" />
      <text x="44" y="156">{new Date(points[0].observed_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</text>
      <text x="368" y="156" textAnchor="end">{new Date(points.at(-1)!.observed_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</text>
      {active && hover !== null ? <g><line x1={x(Math.min(hover, points.length - 1))} x2={x(Math.min(hover, points.length - 1))} y1="14" y2="136" className="chart-cursor" /><circle cx={x(Math.min(hover, points.length - 1))} cy={y(Number(active.equity))} r="3" fill="var(--accent)" /></g> : null}
    </svg>
    <div className="chart-caption">{active ? <span>{money(active.equity, currency)} · {new Date(active.observed_at).toLocaleString()}</span> : <><span className="equity-key">Equity</span><span className="balance-key">Balance</span></>}</div>
    <details className="chart-data"><summary>View recorded values</summary><div className="table-wrap"><table><caption>Recorded equity and balance ({currency})</caption><thead><tr><th scope="col">Time</th><th scope="col">Equity</th><th scope="col">Balance</th></tr></thead><tbody>{points.map(point => <tr key={point.id}><td>{new Date(point.observed_at).toLocaleString()}</td><td>{point.equity}</td><td>{point.balance}</td></tr>)}</tbody></table></div></details>
  </div>;
}

export function OverviewDashboard() {
  const [now, setNow] = useState<Date | null>(null);
  const [accountId, setAccountId] = useState("");
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const operations = useQuery<Operations>({ queryKey: ["automation", "operations"], queryFn: () => api("/automation/operations"), refetchInterval: 10_000 });
  const health = useQuery<Health>({ queryKey: ["operations", "health"], queryFn: () => api("/operations/health"), refetchInterval: 15_000 });
  const research = useQuery<Resource[]>({ queryKey: ["research", "runs"], queryFn: () => api("/research/runs"), refetchInterval: 15_000 });
  const strategies = useQuery<Resource[]>({ queryKey: ["strategies", "drafts"], queryFn: () => api("/strategies"), refetchInterval: 15_000 });
  const ownedAccounts = accounts.data?.filter(account => account.state !== "DELETED") ?? [];
  const account = ownedAccounts.find(item => item.id === accountId) ?? ownedAccounts[0];
  const history = useQuery<EquityHistory>({ queryKey: ["automation", "equity-history", account?.id], queryFn: () => api(`/automation/equity-history?account_id=${account!.id}`), enabled: Boolean(account), refetchInterval: 10_000 });
  const limits = useQuery<Limits>({ queryKey: ["configuration", "limits", account?.id], queryFn: () => api(`/configuration/effective-limits?account_id=${account!.id}`), enabled: Boolean(account) });
  const currency = String(history.data?.currency || account?.currency || "USD");
  const points = (history.data?.points ?? []).filter(point => point.equity != null && point.balance != null && Number.isFinite(Number(point.equity)) && Number.isFinite(Number(point.balance)) && Number.isFinite(Date.parse(point.observed_at))).sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
  const latest = points.at(-1);
  const change = points.length > 1 && Number(points[0].equity) > 0 ? (Number(latest!.equity) / Number(points[0].equity) - 1) * 100 : null;
  const age = now && latest ? now.getTime() - Date.parse(latest.observed_at) : null;
  const live = !history.isError && age !== null && age >= 0 && age < 60_000;
  const dailyLimit = limits.data?.effective.MAX_DAILY_LOSS;
  const dailyLimitLabel = limits.isError ? "Unavailable" : dailyLimit ? dailyLimit.unit === "account_currency" ? money(dailyLimit.value, currency) : `${dailyLimit.value}${dailyLimit.unit === "percent" ? "%" : ` ${dailyLimit.unit}`}` : "Not set";
  const healthy = !health.isError && health.data?.state === "HEALTHY";
  const healthLabel = health.isError ? "Health unavailable" : health.isPending ? "Checking system" : healthy ? "System Healthy" : "Attention required";
  const todayCount = (items: Resource[] | undefined) => now && items ? `+${items.filter(item => new Date(item.created_at).toDateString() === now.toDateString()).length} today` : "—";
  const trades = operations.data?.active_trades.filter(item => !["CLOSED", "CANCELLED", "DELETED", "EXITED"].includes(item.state));
  const metrics: { label: string; value: number | undefined; detail: string; icon: OverviewIconName; tone: string; href: "/configuration" | "/trading" | "/operations"; error: boolean }[] = [
    { label: "Trading accounts", value: accounts.data ? ownedAccounts.length : undefined, detail: todayCount(ownedAccounts), icon: "account", tone: "violet", href: "/configuration", error: accounts.isError },
    { label: "Active broker trades", value: trades?.length, detail: trades?.length === 0 ? "No open trades" : "Reconciled positions", icon: "trend", tone: "green", href: "/trading", error: operations.isError },
    { label: "Trade Plans", value: operations.data?.trade_plans.length, detail: todayCount(operations.data?.trade_plans), icon: "plan", tone: "blue", href: "/trading", error: operations.isError },
    { label: "Execution commands", value: operations.data?.execution_commands.length, detail: todayCount(operations.data?.execution_commands), icon: "terminal", tone: "red", href: "/operations", error: operations.isError },
  ];
  const latestRuns = [...(research.data ?? [])].filter(run => run.state !== "DELETED").sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).filter((run, index, all) => all.findIndex(other => other.account_id === run.account_id) === index);
  const suggestions = latestRuns.flatMap(run => ((run.lane_results ?? []) as Lane[]).flatMap((lane, index) => {
    if (lane.status !== "READY" || !lane.candidate) return [];
    const candidate = lane.candidate;
    // A symbol alone cannot distinguish two instrument wrappers in the same run.
    const unambiguous = ((run.lane_results ?? []) as Lane[]).filter(other => other.candidate?.listing.symbol === candidate.listing.symbol).length === 1;
    const draft = unambiguous ? [...(strategies.data ?? [])].filter(item => item.state !== "DELETED").sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).find(item => {
      const basis = item.research_basis as { market_research_run_id?: string; instrument?: string } | undefined;
      return basis?.market_research_run_id === run.id && basis?.instrument === candidate.listing.symbol;
    }) : undefined;
    const setup = draft?.trade_setup as { status: string; expires_at?: string } | undefined;
    const valid = now && setup?.expires_at && Date.parse(setup.expires_at) > now.getTime();
    const expired = now && setup?.expires_at && Date.parse(setup.expires_at) <= now.getTime();
    const status = strategies.isError ? "Unavailable" : expired || setup?.status === "STALE" ? "Stale" : setup?.status === "SIGNAL" ? valid ? "Setup found" : "Watch" : setup?.status === "NO_TRADE" ? "No trade" : "Watch";
    return [{ id: `${run.id}:${index}`, symbol: candidate.listing.symbol, asset: candidate.listing.asset_class ?? candidate.lane?.asset_class ?? "MARKET", score: candidate.score, status }];
  })).sort((a, b) => b.score - a.score).slice(0, 3);
  const recent = [
    ...(research.data ?? []).filter(item => item.state !== "DELETED").map(item => ({ id: item.id, date: item.created_at, title: "Market research", detail: `${((item.lane_results ?? []) as Lane[]).filter(lane => lane.status === "READY").length} pairs selected · ${item.state.toLowerCase().replaceAll("_", " ")}`, icon: "research" as const, tone: "green", href: "/research" as const })),
    ...(strategies.data ?? []).filter(item => item.state !== "DELETED").map(item => ({ id: item.id, date: item.created_at, title: "Strategy research", detail: (item.proposed_specification as { name?: string } | undefined)?.name ?? item.state.toLowerCase().replaceAll("_", " "), icon: "idea" as const, tone: "violet", href: "/strategies" as const })),
  ].sort((a, b) => Date.parse(b.date) - Date.parse(a.date)).slice(0, 4);

  return <section className="overview">
    <header className="overview-header">
      <div className="overview-heading"><p className="eyebrow">Operations / Overview</p><h1>Autonomous trading command center</h1></div>
      <div className="overview-utilities">
        <Link href="/operations" className="overview-utility"><span className={`health-dot ${healthy ? "is-healthy" : "is-warning"}`} /><span>{healthLabel}<small>{healthy ? "All services operational" : "View dependency status"}</small></span></Link>
        <div className="overview-utility overview-clock"><OverviewIcon name="calendar" /><span>{now ? now.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "Local time"}<small>{now ? `${now.toLocaleTimeString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})` : "Synchronizing…"}</small></span></div>
      </div>
      <p className="overview-subtitle">Evidence, live account equity, policy constraints, and broker execution state in one owner-scoped view.</p>
    </header>

    <section className="overview-metrics" aria-label="Account summary">{metrics.map(metric => <Link className="overview-panel overview-metric" key={metric.label} href={metric.href}>
      <span className={`overview-icon ${metric.tone}`}><OverviewIcon name={metric.icon} /></span>
      <div><span className="metric-label">{metric.label}</span><strong className="metric-value">{metric.error ? "—" : metric.value ?? "—"}</strong><small className={metric.detail.startsWith("+") && !metric.error ? "good" : "muted"}>{metric.error ? "Data unavailable" : metric.value === undefined ? "Loading…" : metric.detail}</small></div>
    </Link>)}</section>

    <section className="overview-panel overview-safety" aria-labelledby="safety-heading">
      <h2 id="safety-heading">Safety state</h2><strong className={healthy ? "good" : "warn"}>{health.isError ? "UNAVAILABLE" : health.data?.state ?? "CHECKING"}</strong>
      <p className="safety-components">{health.isError ? "Dependency status could not be retrieved. Check Operations before proceeding." : health.data?.components.map(item => `${item.component}: ${item.state}`).join(" · ") || "Measuring dependencies…"}</p>
      <p>Execution mode: {operations.isError ? "unavailable" : operations.data?.execution_mode ?? "loading"}. Trade commands remain subject to permission profiles, risk revalidation, and kill switches.</p>
    </section>

    <div className="overview-detail-grid">
      <article className="overview-panel overview-equity" aria-labelledby="equity-heading">
        <div className="panel-heading"><h2 id="equity-heading">Account Equity <span>({live ? "Live" : "Recorded"})</span></h2></div>
        {ownedAccounts.length ? <select className="equity-account" aria-label="Equity account" value={account?.id ?? ""} onChange={event => setAccountId(event.target.value)}>{ownedAccounts.map(item => <option value={item.id} key={item.id}>{String(item.name ?? item.id)}</option>)}</select> : null}
        <div className="equity-headline"><strong>{money(latest?.equity, currency)}</strong>{change !== null ? <span className={change < 0 ? "bad" : "good"}>{change > 0 ? "+" : ""}{change.toFixed(1)}% <small>in view</small></span> : null}</div>
        {history.isError || accounts.isError ? <p className="overview-empty">Equity history unavailable. {latest ? "Showing last recorded values." : "Try again when the connection is restored."}</p> : null}
        {points.length > 1 ? <EquityChart points={points} currency={currency} /> : <div className="overview-empty equity-empty">{accounts.isPending || (account && history.isPending) ? "Loading account history…" : !account ? <><span>No trading account yet.</span><Link href="/configuration">Configure an account →</Link></> : "The chart will appear after two broker snapshots are recorded."}</div>}
        <div className="equity-footer"><span>Starting Equity <strong>{money(account?.starting_balance, currency)}</strong></span><span>Max Daily Loss <strong>{account && limits.isPending ? "…" : dailyLimitLabel}</strong></span></div>
        {latest ? <small className="equity-timestamp">Last snapshot {relativeTime(latest.observed_at, now)}{history.isError ? " · connection unavailable" : ""}</small> : null}
      </article>

      <article className="overview-panel overview-suggestions" aria-labelledby="suggestions-heading">
        <div className="panel-heading"><h2 id="suggestions-heading">Top 3 Trade Suggestions <span>(Latest)</span></h2><Link className="panel-arrow" href="/strategies" aria-label="View all trade suggestions"><OverviewIcon name="chevron" /></Link></div>
        {research.isError ? <p className="overview-empty">Trade suggestions unavailable.</p> : research.isPending ? <p className="overview-empty">Loading market research…</p> : suggestions.length ? <ul className="suggestion-list">{suggestions.map(item => {
          const asset = item.asset.toUpperCase();
          const tone = asset === "METALS" ? "gold" : asset === "CRYPTOCURRENCY" || asset === "CRYPTO" ? "orange" : "blue";
          const label = asset === "CRYPTOCURRENCY" ? "Crypto" : asset.charAt(0) + asset.slice(1).toLowerCase();
          return <li key={item.id}><Link className="suggestion-row" href="/strategies"><span className={`asset-icon ${tone}`} aria-hidden="true">{tone === "gold" ? <OverviewIcon name="metals" /> : tone === "orange" ? item.symbol.startsWith("BTC") ? "₿" : "◇" : tone === "blue" && asset === "FOREX" ? "⇄" : "↗"}</span><span className="suggestion-name"><strong>{item.symbol}</strong><small>{label}</small></span><span className={`suggestion-status ${item.status === "Setup found" ? "signal" : item.status === "Watch" ? "watch" : "neutral"}`}>{item.status}</span><OverviewIcon name="chevron" /></Link></li>;
        })}</ul> : <div className="overview-empty"><span>No selected pairs yet.</span><Link href="/research">Start market research →</Link></div>}
        <p className="panel-footnote">Research signals · review strategy conditions before entry</p>
      </article>

      <article className="overview-panel overview-recent" aria-labelledby="recent-heading">
        <div className="panel-heading"><h2 id="recent-heading">Recent Research</h2><Link href={{ pathname: "/extras", query: { folder: "market-research" } }}>View all</Link></div>
        {research.isError || strategies.isError ? <p className="overview-empty">Some research activity is unavailable.</p> : null}
        {recent.length ? <ul className="research-list">{recent.map(item => <li key={item.id}><Link href={item.href}><span className={`overview-icon ${item.tone}`}><OverviewIcon name={item.icon} /></span><span className="research-copy"><strong>{item.title}</strong><small title={item.detail}>{item.detail}</small></span><time dateTime={item.date} title={new Date(item.date).toLocaleString()}>{relativeTime(item.date, now)}</time></Link></li>)}</ul> : <div className="overview-empty">{research.isPending || strategies.isPending ? "Loading research activity…" : "Completed and ongoing research will appear here."}</div>}
      </article>
    </div>
  </section>;
}
