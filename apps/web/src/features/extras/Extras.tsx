"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { Disclosure } from "@/components/Disclosure";
import { ProgressiveList } from "@/components/ProgressiveList";
import { api, API_ROOT } from "@/lib/api";

type Folder = { id: string; label: string; description: string; count: number };
type ExtraItem = {
  id: string;
  folder: string;
  kind?: string;
  cycle_type?: string;
  state?: string;
  name?: string;
  language?: string;
  code?: string | null;
  artifact_hash?: string;
  reason?: unknown;
  why?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  details?: Record<string, unknown>;
  artifact?: Record<string, unknown>;
  created_at?: string;
  instrument?: string;
  action?: string;
  direction?: string;
  updated_at?: string | number;
  completed_at?: string;
  account_id?: string;
  download_path?: string;
};
type ExtrasResponse = { folders: Folder[]; items: Record<string, ExtraItem[]> };
type AgentReview = { logical_id: string; status: string; raw_decision?: string; evidence?: string[]; score_adjustments?: Record<string, number> };
type LaneResult = {
  lane?: { asset_class?: string; instrument_type?: string };
  status?: string;
  reason_code?: string;
  failure_detail?: string;
  completed_at?: string;
  binding_id?: string;
  observed_candidates?: string[];
  exclusions?: string[];
  source_cut_refs?: string[];
  agent_reviews?: AgentReview[];
  candidate?: { listing?: { symbol?: string; venue?: string }; score?: number; evidence?: string[] };
};

const fallbackFolders: Folder[] = [
  { id: "market-research", label: "Market research", description: "Autonomous market cycles", count: 0 },
  { id: "strategy-research", label: "Strategy research", description: "Strategy hypotheses and validation", count: 0 },
  { id: "trade-recommendations", label: "Trade recommendations", description: "Recommendations and reasons", count: 0 },
  { id: "generated-code", label: "Generated code", description: "Inspectable strategy evaluators", count: 0 },
  { id: "mt5-bridge-ea", label: "MT5 bridge EA", description: "Read-only MQL5 snapshot publisher", count: 0 },
];

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function ResearchDecisionEvidence({ details }: { details?: Record<string, unknown> }) {
  const value = details?.lane_results;
  const lanes = Array.isArray(value) ? value as LaneResult[] : [];
  if (!lanes.length) return null;
  return <details>
    <summary>Research decision evidence</summary>
    <div className="inset form-stack">
      {lanes.map((lane, laneIndex) => {
        const reviews = lane.agent_reviews ?? [];
        const adjustments = reviews.flatMap(review => Object.entries(review.score_adjustments ?? {}).map(([symbol, score]) => `${symbol} ${score >= 0 ? "+" : ""}${score}`));
        return <article className="card form-stack" key={`${lane.lane?.asset_class}-${lane.lane?.instrument_type}-${laneIndex}`}>
          <div className="split-heading"><strong>{lane.lane?.asset_class ?? "UNKNOWN"} · {lane.lane?.instrument_type ?? "UNKNOWN"}</strong><span className={`status ${(lane.status ?? "unknown").toLowerCase()}`}>{lane.status ?? "UNKNOWN"}</span></div>
          <dl>
            <dt>Selected candidate</dt><dd>{lane.candidate?.listing?.symbol ? `${lane.candidate.listing.symbol} · ${lane.candidate.listing.venue ?? "unknown venue"}${typeof lane.candidate.score === "number" ? ` · score ${lane.candidate.score.toFixed(2)}` : ""}` : "None"}</dd>
            <dt>Reason code</dt><dd>{lane.reason_code ?? "None — candidate passed"}</dd>
            <dt>Provider / runtime detail</dt><dd>{lane.failure_detail ?? "None"}</dd>
            <dt>Completed</dt><dd>{lane.completed_at ? new Date(lane.completed_at).toLocaleString() : "Not retained"}</dd>
            <dt>Provider binding</dt><dd>{lane.binding_id ?? "Not retained"}</dd>
            <dt>Candidates evaluated</dt><dd>{(lane.observed_candidates ?? []).join(", ") || "None retained"}</dd>
            <dt>Blocking checks / exclusions</dt><dd>{(lane.exclusions ?? []).join(", ") || "None"}</dd>
            <dt>Source snapshots</dt><dd>{(lane.source_cut_refs ?? []).join(", ") || "None retained"}</dd>
          </dl>
          {lane.candidate?.evidence?.length ? <><h4>Candidate evidence</h4><ul>{lane.candidate.evidence.map((evidence, index) => <li key={`${index}-${evidence}`}>{evidence}</li>)}</ul></> : null}
          {reviews.length ? <><h4>Agent decision trace</h4><ol className="record-list">{reviews.map((review, reviewIndex) => <li key={`${review.logical_id}-${reviewIndex}`}><strong>{review.logical_id.replaceAll("_", " ")} · {review.status}</strong>{review.raw_decision && review.raw_decision.toUpperCase() !== review.status ? <span>Raw verdict: {review.raw_decision}</span> : null}{review.evidence?.length ? <ul>{review.evidence.map((evidence, index) => <li key={`${index}-${evidence}`}>{evidence}</li>)}</ul> : <small>No evidence text returned.</small>}</li>)}</ol>{adjustments.length ? <small>Score adjustments: {adjustments.join(" · ")}</small> : null}</> : <p className="muted">No agent decision trace was retained for this lane.</p>}
        </article>;
      })}
    </div>
  </details>;
}

function recordTitle(item: ExtraItem): string {
  const title = item.name || item.summary?.instrument || item.details?.instrument || item.instrument;
  return title ? display(title) : item.id;
}

function recordTimestamp(item: ExtraItem): number | null {
  const value = item.completed_at ?? item.updated_at ?? item.created_at;
  const timestamp = typeof value === "number" ? value * (value < 1e12 ? 1000 : 1) : Date.parse(value ?? "");
  return Number.isFinite(timestamp) ? timestamp : null;
}

function downloadUrl(path: string): string {
  // API_ROOT already includes /api/v1; the EA download path also includes it.
  return `${API_ROOT}${path.startsWith("/api/v1/") ? path.slice("/api/v1".length) : path}`;
}

function ExtrasFolder({ folder, items, pending, error }: { folder: Folder; items: ExtraItem[]; pending: boolean; error: Error | null }) {
  const [search, setSearch] = useState("");
  const [state, setState] = useState("all");
  const [copyState, setCopyState] = useState<{ id: string; status: "copied" | "failed" } | null>(null);
  const statuses = [...new Set(items.flatMap(item => item.state ? [item.state] : []))].sort();
  const query = search.trim().toLowerCase();
  const filtered = useMemo(() => items.filter(item => {
    const text = [recordTitle(item), item.id, item.account_id, item.state, item.cycle_type, item.kind, item.summary?.instrument, item.summary?.category, item.details?.instrument].map(value => display(value)).join(" ").toLowerCase();
    return (!query || text.includes(query)) && (state === "all" || item.state === state);
  }).sort((left, right) => (recordTimestamp(right) ?? 0) - (recordTimestamp(left) ?? 0)), [items, query, state]);

  const copyCode = async (item: ExtraItem) => {
    let textarea: HTMLTextAreaElement | null = null;
    try {
      const code = String(item.code ?? "");
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        textarea = document.createElement("textarea");
        textarea.value = code;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        if (!document.execCommand("copy")) throw new Error("copy command failed");
      }
      setCopyState({ id: item.id, status: "copied" });
    } catch {
      setCopyState({ id: item.id, status: "failed" });
    } finally {
      textarea?.remove();
    }
  };

  return <section className="section-stack" aria-label={`${folder.label} archive`}>
    <header className="card extras-folder-header">
      <div><p className="eyebrow">Folder</p><h2>{folder.label}</h2><p className="muted">{folder.description}</p></div>
      <small className="muted">{pending ? "Loading records…" : error ? "Records unavailable" : `${items.length} records · newest first`}</small>
    </header>
    <div className="card extras-filters">
      <label>Search this folder<input type="search" placeholder="Instrument, title, account or record ID" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <label>Record status<select value={state} onChange={event => setState(event.target.value)}><option value="all">All statuses</option>{statuses.map(status => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label>
      {search || state !== "all" ? <button type="button" className="btn compact" onClick={() => { setSearch(""); setState("all"); }}>Clear filters</button> : null}
    </div>
    {pending ? <p className="empty card">Loading archived evidence…</p> : error ? <p className="notice bad" role="alert">Unable to load Extras: {error.message}</p> : filtered.length ? <ProgressiveList items={filtered} label="archive records" scopeKey={JSON.stringify([folder.id, query, state])}>{visible => <div className="extras-items">{visible.map(item => {
      const timestamp = recordTimestamp(item);
      const sourceCode = folder.id === "generated-code" || folder.id === "mt5-bridge-ea";
      const reason = item.summary?.reason ?? item.reason;
      return <article className="card extras-item" key={item.id}>
        <div className="split-heading">
          <div><p className="eyebrow">{item.cycle_type?.replaceAll("_", " ") ?? item.kind?.replaceAll("_", " ") ?? folder.label}</p><h3>{recordTitle(item)}</h3></div>
          {item.state ? <span className={`status ${item.state.toLowerCase()}`}>{item.state.replaceAll("_", " ")}</span> : null}
        </div>
        <div className="extras-record-summary">
          <span>{timestamp !== null ? <time dateTime={new Date(timestamp).toISOString()}>{item.completed_at ? "Completed" : "Updated"} {new Date(timestamp).toLocaleString()}</time> : "Timestamp unavailable"}</span>
          {item.summary?.category ? <span>{display(item.summary.category)}</span> : null}
          {item.account_id ? <span>Account {item.account_id}</span> : null}
          {sourceCode ? <span>{item.language ?? (folder.id === "mt5-bridge-ea" ? "mql5" : "python")}</span> : null}
        </div>
        {reason ? <p className={["DEGRADED", "FAILED", "REJECTED"].includes(item.state ?? "") ? "notice warn extras-reason" : "muted extras-reason"}>{display(reason).slice(0, 240)}{display(reason).length > 240 ? "…" : ""}</p> : null}
        {sourceCode ? <>
          <div className="actions">
            {item.code ? <button type="button" className="btn compact" onClick={() => void copyCode(item)}>{copyState?.id === item.id && copyState.status === "copied" ? "Copied" : folder.id === "mt5-bridge-ea" ? "Copy .mq5 code" : "Copy code"}</button> : null}
            {folder.id === "mt5-bridge-ea" && item.download_path ? <a className="btn compact primary" href={downloadUrl(item.download_path)}>Download .mq5</a> : null}
          </div>
          {copyState?.id === item.id && copyState.status === "failed" ? <p className="notice bad" role="alert">Clipboard access was blocked. Expand the source code and copy it manually.</p> : null}
          {item.code ? <Disclosure title="View source code"><pre aria-label={`Source code for ${recordTitle(item)}`}><code>{item.code}</code></pre></Disclosure> : <p className="notice warn">The source artifact is unavailable.</p>}
          <Disclosure title="Artifact metadata"><dl><dt>Artifact</dt><dd>{item.id}</dd><dt>Language</dt><dd>{item.language ?? (folder.id === "mt5-bridge-ea" ? "mql5" : "python")}</dd><dt>SHA-256</dt><dd>{item.artifact_hash ?? "Not retained"}</dd></dl></Disclosure>
        </> : folder.id === "trade-recommendations" ? <>
          <p><span className="muted">Recommendation:</span> {display(item.details?.action ?? item.details?.direction ?? item.action ?? item.direction ?? item.reason)}</p>
          <Disclosure title="Recommendation reasoning"><pre>{display(item.why)}</pre></Disclosure>
          <Disclosure title="Record details"><pre>{display(item.details)}</pre></Disclosure>
        </> : <>
          <Disclosure title="Record details"><dl><dt>Record ID</dt><dd>{item.id}</dd><dt>Account</dt><dd>{item.account_id ?? "Not retained"}</dd><dt>Instrument</dt><dd>{display(item.summary?.instrument)}</dd><dt>Category</dt><dd>{display(item.summary?.category)}</dd><dt>Reason / outcome</dt><dd>{display(reason)}</dd></dl>{item.artifact ? <p className="muted">Archive: {display(item.artifact.relative_path)} · checksum {String(item.artifact.checksum ?? "").slice(0, 16)}…</p> : null}</Disclosure>
          {folder.id === "market-research" ? <ResearchDecisionEvidence details={item.details} /> : null}
          <Disclosure title="Raw archived cycle record"><pre>{display(item.details)}</pre></Disclosure>
        </>}
      </article>;
    })}</div>}</ProgressiveList> : <div className="empty card">{items.length ? <><p>No records match these filters.</p><button type="button" className="btn compact" onClick={() => { setSearch(""); setState("all"); }}>Show all records</button></> : <p>No records in this folder yet. New evidence will appear here automatically.</p>}</div>}
  </section>;
}

export function Extras() {
  const searchParams = useSearchParams();
  const requestedFolder = searchParams.get("folder") ?? "market-research";
  const overview = useQuery<ExtrasResponse>({ queryKey: ["extras", "overview"], queryFn: () => api("/extras/overview"), refetchInterval: 15_000 });
  const folders = overview.data?.folders ?? fallbackFolders;
  const selected = folders.find(item => item.id === requestedFolder) ?? folders[0] ?? fallbackFolders[0];
  return <section className="section-stack">
    <header><p className="eyebrow">Evidence archive</p><h1>Extras</h1><p className="muted">Browse research, trade reasoning and source artifacts. Each folder starts with its three newest records; expand only the evidence you need.</p></header>
    <div className="extras-layout">
      <nav className="card extras-folders" aria-label="Extras folders">
        <h2>Folders</h2>
        {folders.map(item => <Link className={`folder-button ${selected.id === item.id ? "selected" : ""}`} key={item.id}
          href={{ pathname: "/extras", query: { folder: item.id } }} scroll={false} aria-current={selected.id === item.id ? "page" : undefined}>
          <span>{item.label}</span><small aria-label={`${item.count} records`}>{item.count}</small>
        </Link>)}
      </nav>
      <ExtrasFolder key={selected.id} folder={selected} items={overview.data?.items?.[selected.id] ?? []} pending={overview.isPending} error={overview.error} />
    </div>
  </section>;
}
