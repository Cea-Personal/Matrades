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
  download_path?: string;
};
type ExtrasResponse = { folders: Folder[]; items: Record<string, ExtraItem[]> };

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
          {selected === "generated-code" || selected === "mt5-bridge-ea" ? <><div className="actions"><dl><dt>Language</dt><dd>{item.language ?? "python"}</dd><dt>Artifact</dt><dd>{item.id}</dd><dt>SHA-256</dt><dd>{item.artifact_hash ?? "—"}</dd></dl>{selected === "mt5-bridge-ea" && item.code ? <button type="button" className="btn" onClick={() => void copyCode(String(item.code))}> {copyState === "copied" ? "Copied .mq5 code" : "Copy .mq5 code"}</button> : null}{selected === "mt5-bridge-ea" && item.download_path ? <a className="btn primary" href={`${API_ROOT}${item.download_path}`}>Download .mq5</a> : null}</div>{copyState === "failed" && selected === "mt5-bridge-ea" ? <p className="notice bad">Clipboard access was blocked. Select the code below and copy it manually.</p> : null}{item.code ? <pre aria-label={`Source code for ${item.name ?? item.id}`}><code>{item.code}</code></pre> : <p className="notice warn">The source artifact is unavailable.</p>}</> : selected === "trade-recommendations" ? <><dl><dt>Instrument</dt><dd>{display(item.details?.instrument ?? item.details?.trade_id ?? item.id)}</dd><dt>Recommendation</dt><dd>{display(item.details?.action ?? item.details?.direction ?? item.reason)}</dd></dl><h4>Why</h4><pre>{display(item.why)}</pre></> : <><dl><dt>Completed</dt><dd>{item.completed_at ? new Date(item.completed_at).toLocaleString() : "In progress"}</dd><dt>Instrument</dt><dd>{display(item.summary?.instrument)}</dd><dt>Category</dt><dd>{display(item.summary?.category)}</dd><dt>Reason / outcome</dt><dd>{display(item.summary?.reason)}</dd></dl>{item.artifact ? <p className="muted">Archive: {display(item.artifact.relative_path)} · checksum {String(item.artifact.checksum ?? "").slice(0, 16)}…</p> : null}<details><summary>Cycle details</summary><pre>{display(item.details)}</pre></details></>}
        </article>)}</div> : <p className="empty card">No records are available in this folder yet. Run the autonomous cycle or approve a strategy to populate it.</p>}
      </section>
    </div>
  </section>;
}
