"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MfaDeleteDialog } from "@/components/MfaDeleteDialog";
import { api, type Resource, withStepUp } from "@/lib/api";

type Channel = Resource & { name: string; provider: "TELEGRAM" | "PUSHOVER"; destination: string; health: string; masked_suffix?: string; credential_status?: string };
type Preferences = { in_app: boolean; browser_push: boolean; email: boolean; telegram: boolean; pushover: boolean; urgent_only_external: boolean };

const defaults: Preferences = { in_app: true, browser_push: false, email: false, telegram: false, pushover: false, urgent_only_external: true };

export function NotificationCenter() {
  const client = useQueryClient();
  const notifications = useQuery<Resource[]>({ queryKey: ["operations", "notifications"], queryFn: () => api("/operations/notifications"), refetchInterval: 15_000 });
  const channels = useQuery<Channel[]>({ queryKey: ["operations", "notification-channels"], queryFn: () => api("/operations/notification-channels") });
  const preferences = useQuery<Preferences>({ queryKey: ["operations", "notification-preferences"], queryFn: () => api("/operations/notifications/preferences") });
  const [draft, setDraft] = useState({ name: "", provider: "TELEGRAM" as Channel["provider"], secret: "", destination: "" });
  const [prefsDraft, setPrefsDraft] = useState<Preferences | null>(null);
  const [removalTarget, setRemovalTarget] = useState<Channel | null>(null);
  const [message, setMessage] = useState("");
  const activePreferences = prefsDraft ?? preferences.data ?? defaults;
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["operations"] }); };
  const savePreferences = useMutation({ mutationFn: () => api("/operations/notifications/preferences", { method: "POST", body: JSON.stringify(activePreferences) }), onSuccess: async () => { setPrefsDraft(null); setMessage("Notification preferences saved."); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const createChannel = useMutation({ mutationFn: () => api<Channel>("/operations/notification-channels", { method: "POST", body: JSON.stringify(draft) }), onSuccess: async item => { setDraft({ ...draft, name: "", secret: "", destination: "" }); setMessage(`${item.name} saved. Test it before enabling external delivery.`); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const testChannel = useMutation({ mutationFn: (id: string) => api<Channel>(`/operations/notification-channels/${id}/test`, { method: "POST" }), onSuccess: async item => { setMessage(`${item.name} is reachable.`); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const removeChannel = useMutation({ mutationFn: async (code: string) => { if (!removalTarget) throw new Error("Choose a notification channel"); return withStepUp("notification.change", code, grant => api<Channel>(`/operations/notification-channels/${removalTarget.id}`, { method: "DELETE", headers: { "Step-Up-Grant": grant } })); }, onSuccess: async item => { setRemovalTarget(null); setMessage(`${item.name} removed; delivery history is retained.`); await refresh(); }, onError: (error: Error) => setMessage(error.message) });
  const markRead = useMutation({ mutationFn: (id: string) => api(`/operations/notifications/${id}/read`, { method: "POST" }), onSuccess: () => client.invalidateQueries({ queryKey: ["operations", "notifications"] }) });
  const submit = (event: FormEvent) => { event.preventDefault(); setMessage(""); createChannel.mutate(); };
  const setPreference = (key: keyof Preferences, value: boolean) => setPrefsDraft({ ...activePreferences, [key]: value });

  return <section className="section-stack">
    <div className="split-heading"><div><h2>Notifications</h2><p className="muted">Configure encrypted Telegram and Pushover channels. Test delivery here; urgent-only mode prevents routine research noise.</p></div></div>
    <div className="grid two">
      <form className="card form-stack" onSubmit={submit}><h3>Add notification channel</h3><label>Provider<select value={draft.provider} onChange={event => setDraft({ ...draft, provider: event.target.value as Channel["provider"] })}><option value="TELEGRAM">Telegram</option><option value="PUSHOVER">Pushover</option></select></label><label>Channel name<input required value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label><label>{draft.provider === "TELEGRAM" ? "Bot token" : "Pushover application token"}<input required type="password" value={draft.secret} onChange={event => setDraft({ ...draft, secret: event.target.value })} /></label><label>{draft.provider === "TELEGRAM" ? "Chat ID" : "User key"}<input required value={draft.destination} onChange={event => setDraft({ ...draft, destination: event.target.value })} /></label><button className="btn primary" disabled={createChannel.isPending}>{createChannel.isPending ? "Saving…" : "Save encrypted channel"}</button></form>
      <article className="card form-stack"><h3>Delivery preferences</h3><label><input type="checkbox" checked={activePreferences.in_app} onChange={event => setPreference("in_app", event.target.checked)} /> In-product notifications</label><label><input type="checkbox" checked={activePreferences.telegram} onChange={event => setPreference("telegram", event.target.checked)} /> Telegram</label><label><input type="checkbox" checked={activePreferences.pushover} onChange={event => setPreference("pushover", event.target.checked)} /> Pushover</label><label><input type="checkbox" checked={activePreferences.urgent_only_external} onChange={event => setPreference("urgent_only_external", event.target.checked)} /> External channels receive urgent/critical events only</label><button className="btn primary" disabled={savePreferences.isPending} onClick={() => savePreferences.mutate()}>{savePreferences.isPending ? "Saving…" : "Save preferences"}</button></article>
    </div>
    {message ? <p className="notice">{message}</p> : null}
    <article className="card"><h3>Configured channels</h3>{channels.isPending ? <p>Loading…</p> : channels.data?.length ? <div className="table-wrap"><table><thead><tr><th>Name</th><th>Provider</th><th>Destination</th><th>Health</th><th /></tr></thead><tbody>{channels.data.map(channel => <tr key={channel.id}><td>{channel.name}</td><td>{channel.provider}</td><td>{channel.destination}</td><td><span className={`status ${channel.health.toLowerCase()}`}>{channel.health}</span>{channel.masked_suffix ? <small className="muted"> {channel.masked_suffix}</small> : null}</td><td><div className="actions"><button className="btn compact" disabled={testChannel.isPending} onClick={() => testChannel.mutate(channel.id)}>Test</button><button className="btn compact danger" onClick={() => setRemovalTarget(channel)}>Remove</button></div></td></tr>)}</tbody></table></div> : <p className="empty">No Telegram or Pushover channels configured.</p>}</article>
    <article className="card"><h3>In-product inbox</h3>{notifications.isPending ? <p>Loading…</p> : notifications.data?.length ? <ul className="record-list">{notifications.data.map(item => <li key={item.id}><strong>{String(item.title ?? item.event_type ?? "Notification")}</strong><span>{String(item.message ?? item.body ?? "")}</span><small>Delivery: {String(item.delivery_state ?? item.state ?? "PENDING")}</small>{!item.read && <button className="btn compact" onClick={() => markRead.mutate(item.id)}>Mark read</button>}</li>)}</ul> : <p className="empty">No notifications.</p>}</article>
    {removalTarget ? <MfaDeleteDialog key={removalTarget.id} targetLabel={removalTarget.name} scope="notification.change" busy={removeChannel.isPending} error={removeChannel.error instanceof Error ? removeChannel.error.message : undefined} onCancel={() => setRemovalTarget(null)} onConfirm={code => removeChannel.mutate(code)} /> : null}
  </section>;
}
