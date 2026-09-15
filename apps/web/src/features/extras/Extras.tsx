"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

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

export function Extras() {
  const searchParams = useSearchParams();
  const requestedFolder = searchParams.get("folder");
  const [folder, setFolder] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const overview = useQuery<ExtrasResponse>({ queryKey: ["extras", "overview"], queryFn: () => api("/extras/overview"), refetchInterval: 15_000 });
  const folders = overview.data?.folders ?? fallbackFolders;
  const activeFolder = folder ?? requestedFolder ?? "market-research";
  const selected = folders.some(item => item.id === activeFolder) ? activeFolder : folders[0]?.id ?? "market-research";
  const items = useMemo(() => overview.data?.items?.[selected] ?? [], [overview.data, selected]);
  const copyCode = async (code: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = code;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        if (!document.execCommand("copy")) throw new Error("copy command failed");
        textarea.remove();
      }
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("failed");
    }
  };

  return <section className="section-stack">
    <header><p className="eyebrow">Evidence archive</p><h1>Extras</h1><p className="muted">Timestamped research cycles, trade reasoning, and generated strategy code in one read-only workspace. Select a folder to inspect the evidence behind a decision.</p></header>
    <div className="extras-layout">
      <aside className="card extras-folders" aria-label="Extras folders"><h2>Folders</h2>{folders.map(item => <button className={`folder-button ${selected === item.id ? "selected" : ""}`} key={item.id} onClick={() => setFolder(item.id)}><span>{item.label}</span><small>{item.count}</small></button>)}</aside>
      <section className="section-stack"><div className="card"><p className="eyebrow">Folder</p><h2>{folders.find(item => item.id === selected)?.label ?? selected}</h2><p className="muted">{folders.find(item => item.id === selected)?.description}</p></div>
        {overview.isPending ? <p className="empty card">Loading archived evidence…</p> : overview.error ? <p className="notice bad">Unable to load Extras: {(overview.error as Error).message}</p> : items.length ? <div className="extras-items">{items.map(item => <article className="card extras-item" key={item.id}>
          <div className="split-heading"><div><p className="muted">{item.cycle_type?.replaceAll("_", " ") ?? item.kind?.replaceAll("_", " ")}</p><h3>{item.name ?? display(item.summary?.instrument) ?? item.id}</h3></div>{item.state ? <span className={`status ${item.state.toLowerCase()}`}>{item.state}</span> : null}</div>
          {selected === "generated-code" || selected === "mt5-bridge-ea" ? <><div className="actions"><dl><dt>Language</dt><dd>{item.language ?? "python"}</dd><dt>Artifact</dt><dd>{item.id}</dd><dt>SHA-256</dt><dd>{item.artifact_hash ?? "—"}</dd></dl>{selected === "mt5-bridge-ea" && item.code ? <button type="button" className="btn" onClick={() => void copyCode(String(item.code))}> {copyState === "copied" ? "Copied .mq5 code" : "Copy .mq5 code"}</button> : null}{selected === "mt5-bridge-ea" && item.download_path ? <a className="btn primary" href={`${API_ROOT}${item.download_path}`}>Download .mq5</a> : null}</div>{copyState === "failed" && selected === "mt5-bridge-ea" ? <p className="notice bad">Clipboard access was blocked. Select the code below and copy it manually.</p> : null}{item.code ? <pre aria-label={`Source code for ${item.name ?? item.id}`}><code>{item.code}</code></pre> : <p className="notice warn">The source artifact is unavailable.</p>}</> : selected === "trade-recommendations" ? <><dl><dt>Instrument</dt><dd>{display(item.details?.instrument ?? item.details?.trade_id ?? item.id)}</dd><dt>Recommendation</dt><dd>{display(item.details?.action ?? item.details?.direction ?? item.reason)}</dd></dl><h4>Why</h4><pre>{display(item.why)}</pre></> : <><dl><dt>Completed</dt><dd>{item.completed_at ? new Date(item.completed_at).toLocaleString() : "In progress"}</dd><dt>Account</dt><dd>{item.account_id ?? "—"}</dd><dt>Instrument</dt><dd>{display(item.summary?.instrument)}</dd><dt>Category</dt><dd>{display(item.summary?.category)}</dd><dt>Reason / outcome</dt><dd>{display(item.summary?.reason)}</dd></dl>{item.artifact ? <p className="muted">Archive: {display(item.artifact.relative_path)} · checksum {String(item.artifact.checksum ?? "").slice(0, 16)}…</p> : null}{selected === "market-research" ? <ResearchDecisionEvidence details={item.details} /> : null}<details><summary>Raw archived cycle record</summary><pre>{display(item.details)}</pre></details></>}
        </article>)}</div> : <p className="empty card">No records are available in this folder yet. Run the autonomous cycle or approve a strategy to populate it.</p>}
      </section>
    </div>
  </section>;
}
