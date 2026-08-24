"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Resource } from "@/lib/api";

export function NotificationCenter() {
  const client = useQueryClient();
  const notifications = useQuery<Resource[]>({ queryKey: ["operations", "notifications"], queryFn: () => api("/operations/notifications"), refetchInterval: 15_000 });
  const preferences = useMutation({ mutationFn: (external: boolean) => api("/operations/notifications/preferences", { method: "POST", body: JSON.stringify({ in_app: true, browser_push: false, email: external, telegram: false, urgent_only_external: true }) }) });
  const markRead = useMutation({ mutationFn: (id: string) => api(`/operations/notifications/${id}/read`, { method: "POST" }), onSuccess: () => client.invalidateQueries({ queryKey: ["operations", "notifications"] }) });
  return <section><div className="split-heading"><h2>Notifications</h2><div className="actions"><button className="btn compact" onClick={() => preferences.mutate(false)}>In-product only</button><button className="btn compact" onClick={() => preferences.mutate(true)}>Urgent email</button></div></div>{notifications.isPending ? <p>Loading…</p> : notifications.data?.length ? <ul className="record-list card">{notifications.data.map(item => <li key={item.id}><strong>{String(item.title ?? item.event_type ?? "Notification")}</strong><span>{String(item.message ?? "")}</span>{!item.read && <button className="btn compact" onClick={() => markRead.mutate(item.id)}>Mark read</button>}</li>)}</ul> : <p className="empty card">No notifications.</p>}</section>;
}
