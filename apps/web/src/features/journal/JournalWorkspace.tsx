"use client";

import { useCallback, useEffect, useState } from "react";

import { Journal, type JournalEntryEvidence } from "./Journal";
import { JournalAnalytics, type AnalyticsEvidence } from "./JournalAnalytics";

export function JournalWorkspace() {
  const [entries, setEntries] = useState<JournalEntryEvidence[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsEvidence>();
  const [dimension, setDimension] = useState("instrument");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [entryResponse, analyticsResponse] = await Promise.all([
        fetch("/api/v1/journal/entries", { credentials: "same-origin" }),
        fetch(`/api/v1/journal/analytics?dimension=${encodeURIComponent(dimension)}`, { credentials: "same-origin" })
      ]);
      if (!entryResponse.ok || !analyticsResponse.ok) throw new Error("unavailable");
      setEntries((await entryResponse.json() as { items: JournalEntryEvidence[] }).items);
      setAnalytics(await analyticsResponse.json() as AnalyticsEvidence);
      setError(undefined);
    } catch { setError("TraderX could not load journal evidence."); }
  }, [dimension]);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  async function project() {
    setBusy(true); setError(undefined);
    try {
      const response = await fetch("/api/v1/journal/project", { method: "POST", credentials: "same-origin" });
      const payload = await response.json() as { created?: number; detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Journal projection failed."); return; }
      setMessage(`${payload.created ?? 0} completed activity record(s) added. Existing history was not changed.`);
      await load();
    } catch { setError("TraderX could not project completed activity."); }
    finally { setBusy(false); }
  }

  async function annotate(entryId: string, content: string) {
    setBusy(true); setError(undefined);
    try {
      const response = await fetch(`/api/v1/journal/entries/${entryId}/annotations`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ content }) });
      const payload = await response.json() as { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Annotation was not recorded."); return; }
      setMessage("A new annotation version was appended; prior notes remain preserved.");
      await load();
    } catch { setError("TraderX could not append the annotation."); }
    finally { setBusy(false); }
  }

  async function attach(entryId: string, file: File) {
    setBusy(true); setError(undefined);
    try {
      const body = new FormData(); body.append("file", file);
      const response = await fetch(`/api/v1/journal/entries/${entryId}/attachments`, { method: "POST", credentials: "same-origin", body });
      const payload = await response.json() as { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Screenshot was not attached."); return; }
      setMessage("Protected screenshot evidence attached with an integrity checksum.");
      await load();
    } catch { setError("TraderX could not attach the screenshot."); }
    finally { setBusy(false); }
  }

  async function propose(hypothesis: string) {
    setBusy(true); setError(undefined);
    try {
      const response = await fetch("/api/v1/journal/proposals", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ hypothesis, evidence_entry_ids: selectedIds }) });
      const payload = await response.json() as { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "Research proposal was not created."); return; }
      setMessage("Research proposal created. No strategy or lifecycle state was changed.");
    } catch { setError("TraderX could not create the research proposal."); }
    finally { setBusy(false); }
  }

  function toggle(id: string) { setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  return <div className="governed-workspace"><Journal busy={busy} entries={entries} onAnnotate={annotate} onAttach={attach} onProject={project} onToggle={toggle} selectedIds={selectedIds} /><JournalAnalytics analytics={analytics} busy={busy} dimension={dimension} onDimension={setDimension} onPropose={propose} selectedCount={selectedIds.length} />{message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</div>;
}
