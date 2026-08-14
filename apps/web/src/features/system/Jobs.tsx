"use client";

import { useCallback, useEffect, useState } from "react";

type Job = { id: string; type: string; state: string; progress: Record<string, unknown>; attempt_count: number; result_ref?: string; error_code?: string; available_actions: string[]; created_at?: string };

export function Jobs() {
  const [items, setItems] = useState<Job[]>([]);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState<string>();
  const load = useCallback(async () => { try { const response = await fetch("/api/v1/jobs", { credentials: "same-origin" }); if (!response.ok) throw new Error("unavailable"); setItems((await response.json() as { items: Job[] }).items); setError(undefined); } catch { setError("TraderX could not load durable jobs."); } }, []);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  useEffect(() => {
    const fallback = window.setInterval(() => void load(), 15000);
    const active = items.find((job) => ["QUEUED", "RUNNING", "PAUSED"].includes(job.state));
    if (!active || typeof EventSource === "undefined") return () => window.clearInterval(fallback);
    const events = new EventSource(`/api/v1/jobs/${active.id}/events`, { withCredentials: true });
    events.addEventListener("job", () => void load());
    events.onerror = () => events.close();
    return () => { events.close(); window.clearInterval(fallback); };
  }, [items, load]);
  async function act(job: Job, action: string) { setBusyId(job.id); setError(undefined); try { const response = await fetch(`/api/v1/jobs/${job.id}/actions`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ action }) }); const payload = await response.json() as { detail?: string }; if (!response.ok) { setError(payload.detail ?? "Job action was rejected."); return; } await load(); } catch { setError("TraderX could not record the job action."); } finally { setBusyId(""); } }
  return <section aria-labelledby="jobs"><h3 id="jobs">Background jobs</h3><p>Durable jobs continue without the browser. Pause and cancel requests take effect at safe checkpoints.</p>{items.length ? <div className="evidence-table">{items.map((job) => <div className="evidence-row" key={job.id}><span><strong>{job.type}</strong><small>{job.id.slice(0, 8)} · attempt {job.attempt_count}</small></span><span>{job.state}</span><span>{String(job.progress.stage ?? "Not started")}</span><span className="button-row">{job.available_actions.map((action) => <button className="secondary-button" disabled={busyId === job.id} key={action} onClick={() => void act(job, action)} type="button">{action.toLowerCase()}</button>)}</span></div>)}</div> : <p className="workspace-notice">No background job has been created yet.</p>}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</section>;
}
