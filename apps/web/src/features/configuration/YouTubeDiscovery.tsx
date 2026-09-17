"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

type SearchResponse = { run_id: string; state: string; query: string; discovered: number; videos: { video_id: string; title: string; url: string }[]; provider_requested_at: string };
type TranscriptResponse = { run_id: string; state: string; created: number; skipped: number; failed: unknown[]; transcript_results?: { video_id: string; title: string; status: string }[] };
type Schedule = { configured: boolean; enabled: boolean; run_at: string; timezone: string; weekdays: number[]; next_run_at: string | null; query: string; limit: number; languages: string[]; category: string };
type Run = Resource & { trigger: string; provider_requested_at?: string; scheduled_at?: string; query: string; discovered?: number; created?: number; discovery_stage?: string; discovered_videos?: { video_id: string; title: string; url: string }[] };

export function YouTubeDiscovery() {
  const client = useQueryClient();
  const schedule = useQuery<Schedule>({ queryKey: ["knowledge", "youtube", "schedule"], queryFn: () => api("/knowledge/youtube/schedule") });
  const runs = useQuery<Run[]>({ queryKey: ["knowledge", "youtube", "runs"], queryFn: () => api("/knowledge/youtube/runs"), refetchInterval: 30_000 });
  const [manualInput, setManualInput] = useState({ query: "trading strategy", limit: "5" });
  const [draft, setDraft] = useState<Schedule | null>(null);
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const editable = draft ?? schedule.data;
  const refresh = () => client.invalidateQueries({ queryKey: ["knowledge"] });
  const searchVideos = useMutation({
    mutationFn: () => api<SearchResponse>("/knowledge/youtube/search", { method: "POST", body: JSON.stringify({ query: manualInput.query, limit: Number(manualInput.limit), languages: ["en"], category: "trading" }) }),
    onSuccess: result => { setSearchResult(result); setMessage(`SerpApi found ${result.discovered} videos. Review the results, then fetch their transcripts.`); },
    onError: (error: Error) => setMessage(error.message),
  });
  const fetchTranscripts = useMutation({
    mutationFn: () => { if (!searchResult) throw new Error("Search for videos first"); return api<TranscriptResponse>(`/knowledge/youtube/runs/${searchResult.run_id}/transcripts`, { method: "POST" }); },
    onSuccess: async result => { setMessage(`${result.created} transcript(s) indexed, ${result.skipped} already known, ${result.failed.length} unavailable.`); setSearchResult(null); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const save = useMutation({
    mutationFn: () => { if (!editable) throw new Error("Schedule is still loading"); const { enabled, run_at, timezone, weekdays, query, limit, languages, category } = editable; return api<Schedule>("/knowledge/youtube/schedule", { method: "PUT", body: JSON.stringify({ enabled, run_at, timezone, weekdays, query, limit, languages, category }) }); },
    onSuccess: async result => { setDraft(result); setEditing(false); setMessage("YouTube discovery schedule saved. Every SerpApi call will be timestamped below."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const remove = useMutation({
    mutationFn: () => api<Schedule>("/knowledge/youtube/schedule", { method: "DELETE" }),
    onSuccess: async result => { setDraft(result); setEditing(false); setMessage("YouTube discovery schedule removed. SerpApi will only be called manually."); await refresh(); },
    onError: (error: Error) => setMessage(error.message),
  });
  const change = (patch: Partial<Schedule>) => { if (editable) setDraft({ ...editable, ...patch }); };

  return <article className="card form-stack">
    <h2>YouTube discovery schedule and SerpApi calls</h2>
    <p className="muted">Each scheduled or manual provider call is timestamped here in Connections. Successful captions are written to the owner-scoped knowledge index.</p>
    <form className="form-stack inset" onSubmit={event => { event.preventDefault(); searchVideos.mutate(); }}>
      <h3>Two-stage YouTube knowledge ingestion</h3>
      <p className="muted">First use SerpApi to discover trading videos. Review the returned titles, then fetch their captions, chunk and embed them into the owner-scoped Knowledge base.</p>
      <div className="form-grid">
        <label>Search query<input required value={manualInput.query} onChange={event => setManualInput({ ...manualInput, query: event.target.value })} /></label>
        <label>Videos to inspect<input type="number" min="1" max="20" value={manualInput.limit} onChange={event => setManualInput({ ...manualInput, limit: event.target.value })} /></label>
      </div>
      <div className="actions"><button type="submit" className="btn primary" disabled={searchVideos.isPending || fetchTranscripts.isPending}>{searchVideos.isPending ? "Searching videos…" : "1. Search trading videos"}</button></div>
      {searchResult ? <div className="inset form-stack"><strong>{searchResult.discovered} videos discovered</strong><ul className="record-list">{searchResult.videos.map(video => <li key={video.video_id}><a href={video.url} target="_blank" rel="noreferrer"><strong>{video.title}</strong></a><small>{video.video_id}</small></li>)}</ul><button type="button" className="btn primary" disabled={fetchTranscripts.isPending} onClick={() => fetchTranscripts.mutate()}>{fetchTranscripts.isPending ? "Fetching transcripts…" : "Fetch transcripts for these videos"}</button></div> : null}
    </form>
    {message ? <p className="notice">{message}</p> : null}
    {editable?.configured && !editing ? <div className="inset form-stack">
      <strong>Saved YouTube schedule</strong><span>{editable.enabled ? `${editable.run_at} · ${editable.timezone} · “${editable.query}”` : "Disabled"}</span>
      <small>Next SerpApi call: {editable.next_run_at ? new Date(editable.next_run_at).toLocaleString() : "Schedule disabled"}</small>
      <div className="actions"><button className="btn" onClick={() => setEditing(true)}>Edit / replace schedule</button><button className="btn danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Remove schedule</button></div>
    </div> : editable ? <>
      <div className="form-grid"><label>Scheduled query<input value={editable.query} onChange={event => change({ query: event.target.value })} /></label><label>Videos per call<input type="number" min="1" max="20" value={editable.limit} onChange={event => change({ limit: Number(event.target.value) })} /></label><label>Run time<input type="time" value={editable.run_at} onChange={event => change({ run_at: event.target.value })} /></label><label>Timezone<input value={editable.timezone} onChange={event => change({ timezone: event.target.value })} /></label></div>
      <label><input type="checkbox" checked={editable.enabled} onChange={event => change({ enabled: event.target.checked })} /> Enable scheduled SerpApi discovery</label>
      <fieldset><legend>Run on</legend><div className="actions">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, index) => <label key={day}><input type="checkbox" checked={editable.weekdays.includes(index)} onChange={event => change({ weekdays: event.target.checked ? [...new Set([...editable.weekdays, index])].sort() : editable.weekdays.filter(value => value !== index) })} /> {day}</label>)}</div></fieldset>
      <div className="actions"><button className="btn primary" disabled={save.isPending || !editable.query || (editable.enabled && !editable.weekdays.length)} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : editable.configured ? "Replace YouTube schedule" : "Save YouTube schedule"}</button>{editable.configured ? <button className="btn" onClick={() => { setDraft(null); setEditing(false); }}>Cancel</button> : null}</div>
    </> : <p>Loading schedule…</p>}
    <h3>Recent SerpApi invocation history</h3>
    {runs.data?.length ? <ul className="record-list">{runs.data.map(run => <li key={run.id}><strong>{run.trigger} · {run.state}</strong><span>{run.query}</span><small>Provider called: {run.provider_requested_at ? new Date(run.provider_requested_at).toLocaleString() : run.scheduled_at ? `queued ${new Date(run.scheduled_at).toLocaleString()}` : "not called yet"} · indexed {run.created ?? 0} / discovered {run.discovered ?? 0}</small></li>)}</ul> : <p className="empty">No SerpApi calls recorded yet. Without a saved schedule, calls are manual only.</p>}
  </article>;
}
