"use client";

import { useCallback, useEffect, useState } from "react";

type Notice = { id: string; event_type: string; severity: string; payload: { title?: string; message?: string }; state: string; read_at?: string; created_at: string };
type Preference = { id: string; channel: string; minimum_severity: string; enabled: boolean };

export function Notifications() {
  const [items, setItems] = useState<Notice[]>([]);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const load = useCallback(async () => { try { const [inbox, prefs] = await Promise.all([fetch("/api/v1/notifications/inbox", { credentials: "same-origin" }), fetch("/api/v1/notifications/preferences", { credentials: "same-origin" })]); if (!inbox.ok || !prefs.ok) throw new Error("unavailable"); setItems((await inbox.json() as { items: Notice[] }).items); setPreferences((await prefs.json() as { items: Preference[] }).items); setError(undefined); } catch { setError("TraderX could not load notifications."); } }, []);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function save(channel: string, enabled: boolean, minimum_severity = "WARNING") { setError(undefined); try { const response = await fetch(`/api/v1/notifications/preferences/${channel}`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, enabled, minimum_severity }) }); if (!response.ok) throw new Error("unavailable"); await load(); setMessage(`${channel} preference saved.`); } catch { setError("TraderX could not save the notification preference."); } }
  async function testChannel(channel: string) { try { const response = await fetch(`/api/v1/notifications/channels/${channel}/test`, { method: "POST", credentials: "same-origin" }); if (!response.ok) throw new Error("unavailable"); await load(); setMessage(`${channel} test queued with a durable web inbox copy.`); } catch { setError("TraderX could not test that channel."); } }
  async function markRead(id: string) { await fetch(`/api/v1/notifications/inbox/${id}/read`, { method: "POST", credentials: "same-origin" }); await load(); }
  return <section aria-labelledby="notifications"><h3 id="notifications">Notification inbox and delivery</h3><p>Critical notices stay in the durable web inbox even when an external delivery channel fails.</p><div className="button-row">{["WEB", "EMAIL", "TELEGRAM"].map((channel) => { const preference = preferences.find((item) => item.channel === channel); return <span key={channel}><label className="confirmation-check"><input checked={preference?.enabled ?? channel === "WEB"} onChange={(event) => void save(channel, event.target.checked, preference?.minimum_severity)} type="checkbox" />{channel}</label><button className="secondary-button" onClick={() => void testChannel(channel)} type="button">Test {channel.toLowerCase()}</button></span>; })}</div>{items.length ? <ol className="timeline">{items.map((item) => <li key={item.id}><strong>{item.severity} · {item.payload.title ?? item.event_type}</strong><span>{item.payload.message}</span><small>{new Date(item.created_at).toLocaleString()} · {item.state}</small>{!item.read_at ? <button className="secondary-button" onClick={() => void markRead(item.id)} type="button">Mark read</button> : null}</li>)}</ol> : <p className="workspace-notice">The notification inbox is empty.</p>}{message ? <p className="status-message" role="status">{message}</p> : null}{error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}</section>;
}
