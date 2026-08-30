"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, Resource, withStepUp } from "@/lib/api";

type PermissionKey =
  | "new_entry"
  | "order_cancellation"
  | "stop_loss_create_or_modify"
  | "take_profit_create_or_modify"
  | "partial_close"
  | "full_exit";
type PermissionProfile = Record<PermissionKey, boolean> & {
  account_id: string;
  version: number;
  reason: string;
};
type KillSwitch = { active: boolean; safety_epoch: number; reason: string };
type PendingAction = {
  title: string;
  scope: "execution.permission" | "execution.kill_switch";
  run: (grant: string) => Promise<unknown>;
};

const permissionLabels: Array<[PermissionKey, string]> = [
  ["new_entry", "New entries"],
  ["order_cancellation", "Order cancellation"],
  ["stop_loss_create_or_modify", "Create or change Stop Loss"],
  ["take_profit_create_or_modify", "Create or change Take Profit"],
  ["partial_close", "Partial close"],
  ["full_exit", "Full exit"],
];

function defaults(accountId: string): PermissionProfile {
  return {
    account_id: accountId,
    version: 1,
    reason: "",
    new_entry: false,
    order_cancellation: false,
    stop_loss_create_or_modify: false,
    take_profit_create_or_modify: false,
    partial_close: false,
    full_exit: false,
  };
}

function StepUpDialog({
  action,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  action: PendingAction;
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: (code: string) => void;
}) {
  const [code, setCode] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code) onConfirm(code);
  };
  return <div className="modal-backdrop" role="presentation">
    <form className="card modal form-stack" role="dialog" aria-modal="true" aria-labelledby="automation-step-up" onSubmit={submit}>
      <h2 id="automation-step-up">Confirm automation change</h2>
      <p>{action.title}</p>
      <p className="muted">Enter an authenticator or recovery code. Kill-switch deactivation also requires a fresh broker/account snapshot.</p>
      <label>MFA code<input required autoFocus type="password" value={code} onChange={event => setCode(event.target.value)} /></label>
      {error ? <p className="notice bad">{error}</p> : null}
      <div className="actions"><button className="btn primary" disabled={busy || !code}>{busy ? "Verifying…" : "Verify and apply"}</button><button type="button" className="btn" disabled={busy} onClick={onCancel}>Cancel</button></div>
    </form>
  </div>;
}

export function AutomationControls() {
  const queryClient = useQueryClient();
  const accounts = useQuery<Resource[]>({ queryKey: ["configuration", "accounts"], queryFn: () => api("/configuration/accounts") });
  const [accountId, setAccountId] = useState("");
  const selectedAccount = accountId || accounts.data?.find(item => item.state !== "DELETED")?.id || "";
  const permissions = useQuery<PermissionProfile>({ queryKey: ["automation", "permissions", selectedAccount], queryFn: () => api(`/automation/permissions/${selectedAccount}`), enabled: Boolean(selectedAccount) });
  const platformKill = useQuery<KillSwitch>({ queryKey: ["automation", "kill", "platform"], queryFn: () => api("/automation/kill-switch/platform") });
  const accountKill = useQuery<KillSwitch>({ queryKey: ["automation", "kill", selectedAccount], queryFn: () => api(`/automation/kill-switch/accounts/${selectedAccount}`), enabled: Boolean(selectedAccount) });
  const [draft, setDraft] = useState<PermissionProfile | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [message, setMessage] = useState("");
  const effective = useMemo(() => draft ?? permissions.data ?? defaults(selectedAccount), [draft, permissions.data, selectedAccount]);

  const execute = useMutation({
    mutationFn: (code: string) => {
      if (!pending) throw new Error("Choose an automation change");
      return withStepUp(pending.scope, code, pending.run);
    },
    onSuccess: async () => {
      setMessage("Automation authority updated and versioned.");
      setPending(null);
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["automation"] });
    },
    onError: (error: Error) => setMessage(error.message),
  });
  const requestPermissionSave = () => setPending({
    title: `Apply the six execution permissions for account ${selectedAccount}?`,
    scope: "execution.permission",
    run: grant => api(`/automation/permissions/${selectedAccount}`, { method: "PUT", headers: { "Step-Up-Grant": grant }, body: JSON.stringify({ ...effective, account_id: selectedAccount, version: (permissions.data?.version ?? 0) + 1 }) }),
  });
  const requestKillChange = (scope: "platform" | "account", active: boolean) => setPending({
    title: `${active ? "Activate" : "Deactivate"} the ${scope} kill switch?`,
    scope: "execution.kill_switch",
    run: grant => api(scope === "platform" ? "/automation/kill-switch/platform" : `/automation/kill-switch/accounts/${selectedAccount}`, { method: "PUT", headers: { "Step-Up-Grant": grant }, body: JSON.stringify({ active, reason: active ? "operator safety stop" : "operator restored automation after health verification" }) }),
  });

  const activeAccounts = (accounts.data ?? []).filter(item => item.state !== "DELETED");
  return <section className="section-stack">
    <header><p className="eyebrow">Execution authority</p><h1>Automation controls</h1><p className="muted">Permissions are independent, account-scoped, versioned, and re-read immediately before every broker command. Kill switches are durable and visible.</p></header>
    {message ? <p className={execute.isError ? "notice bad" : "notice good"}>{message}</p> : null}
    <article className="card form-stack">
      <h2>Safety stops</h2>
      <div className="grid two">
        <div><strong>Platform</strong><p className="muted">Epoch {platformKill.data?.safety_epoch ?? 0} · {platformKill.data?.active ? "STOPPED" : "RUNNING"}</p><button className={platformKill.data?.active ? "btn primary" : "btn"} onClick={() => requestKillChange("platform", !platformKill.data?.active)}>{platformKill.data?.active ? "Deactivate after health check" : "Activate immediately"}</button></div>
        <div><strong>Selected account</strong><p className="muted">Epoch {accountKill.data?.safety_epoch ?? 0} · {accountKill.data?.active ? "STOPPED" : "RUNNING"}</p><button className={accountKill.data?.active ? "btn primary" : "btn"} disabled={!selectedAccount} onClick={() => requestKillChange("account", !accountKill.data?.active)}>{accountKill.data?.active ? "Deactivate after health check" : "Activate immediately"}</button></div>
      </div>
    </article>
    <article className="card form-stack">
      <h2>Account command permissions</h2>
      {activeAccounts.length ? <><label>Trading account<select value={selectedAccount} onChange={event => { setAccountId(event.target.value); setDraft(null); }}>{activeAccounts.map(item => <option key={item.id} value={item.id}>{String(item.name)} · {item.id}</option>)}</select></label>
        <div className="grid two">{permissionLabels.map(([key, label]) => <label key={key}><input type="checkbox" checked={Boolean(effective[key])} onChange={event => setDraft({ ...effective, [key]: event.target.checked })} /> {label}</label>)}</div>
        <label>Change reason<input value={effective.reason} onChange={event => setDraft({ ...effective, reason: event.target.value })} placeholder="Why these permissions are appropriate" /></label>
        <button className="btn primary" disabled={!selectedAccount || execute.isPending} onClick={requestPermissionSave}>Save versioned permissions</button></> : <p className="empty">Configure a trading account first.</p>}
    </article>
    {pending ? <StepUpDialog action={pending} busy={execute.isPending} error={execute.error instanceof Error ? execute.error.message : undefined} onCancel={() => setPending(null)} onConfirm={code => execute.mutate(code)} /> : null}
  </section>;
}
