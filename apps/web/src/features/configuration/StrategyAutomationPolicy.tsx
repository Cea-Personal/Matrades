"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type Policy = {
  account_id: string;
  enabled: boolean;
  backtest_lookback_days: number;
  paper_duration_days: number;
  max_paper_attempts: number;
  spread: string;
  commission: string;
  slippage: string;
};

const defaults: Omit<Policy, "account_id"> = { enabled: false, backtest_lookback_days: 90, paper_duration_days: 30, max_paper_attempts: 1, spread: "0.0001", commission: "0", slippage: "0.00005" };

export function StrategyAutomationPolicy({ accounts }: { accounts: Resource[] }) {
  const client = useQueryClient();
  const [accountId, setAccountId] = useState("");
  const selected = accounts.some(item => item.id === accountId) ? accountId : accounts[0]?.id ?? "";
  const policy = useQuery<Policy>({ queryKey: ["configuration", "strategy-automation", selected], queryFn: () => api(`/configuration/accounts/${selected}/strategy-automation`), enabled: Boolean(selected) });
  const [draft, setDraft] = useState<{ accountId: string; values: typeof defaults } | null>(null);
  const [message, setMessage] = useState("");
  const loaded = policy.data ? { enabled: policy.data.enabled, backtest_lookback_days: policy.data.backtest_lookback_days, paper_duration_days: policy.data.paper_duration_days, max_paper_attempts: policy.data.max_paper_attempts, spread: String(policy.data.spread), commission: String(policy.data.commission), slippage: String(policy.data.slippage) } : defaults;
  const form = draft?.accountId === selected ? draft.values : loaded;
  const setForm = (values: typeof defaults) => setDraft({ accountId: selected, values });
  const save = useMutation({
    mutationFn: () => api(`/configuration/accounts/${selected}/strategy-automation`, { method: "PUT", body: JSON.stringify({ ...form, spread: Number(form.spread), commission: Number(form.commission), slippage: Number(form.slippage) }) }),
    onSuccess: async () => { setMessage(form.enabled ? "Autonomous validation enabled. Live activation and execution remain manual." : "Autonomous validation disabled."); await client.invalidateQueries({ queryKey: ["configuration", "strategy-automation", selected] }); },
    onError: (error: Error) => setMessage(error.message),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); setMessage(""); save.mutate(); };
  return <form className="card form-stack" onSubmit={submit}>
    <h2>Autonomous strategy validation</h2>
    <p>One owner authorization lets successful market selections progress through proposal acceptance, immutable versioning, formal backtesting, forward paper testing, and paper review. Activation, Trade Plans, and broker execution remain manual.</p>
    {accounts.length ? <>
      <label>Trading account<select value={selected} onChange={event => setAccountId(event.target.value)}>{accounts.map(item => <option key={item.id} value={item.id}>{String(item.name)}</option>)}</select></label>
      <label><input type="checkbox" checked={form.enabled} onChange={event => setForm({ ...form, enabled: event.target.checked })} /> Enable autonomous validation</label>
      <div className="form-grid">
        <label>Backtest lookback days<input type="number" min={7} max={365} value={form.backtest_lookback_days} onChange={event => setForm({ ...form, backtest_lookback_days: Number(event.target.value) })} /></label>
        <label>Paper duration days<input type="number" min={1} max={90} value={form.paper_duration_days} onChange={event => setForm({ ...form, paper_duration_days: Number(event.target.value) })} /></label>
        <label>Maximum paper attempts<input type="number" min={1} max={5} value={form.max_paper_attempts} onChange={event => setForm({ ...form, max_paper_attempts: Number(event.target.value) })} /></label>
        <label>Spread cost<input type="number" min="0" step="any" value={form.spread} onChange={event => setForm({ ...form, spread: event.target.value })} /></label>
        <label>Commission<input type="number" min="0" step="any" value={form.commission} onChange={event => setForm({ ...form, commission: event.target.value })} /></label>
        <label>Slippage<input type="number" min="0" step="any" value={form.slippage} onChange={event => setForm({ ...form, slippage: event.target.value })} /></label>
      </div>
      <p className="muted">Active MAX DAILY LOSS and MAX TOTAL DRAWDOWN rules are required. Failed or blocked stages stop safely and remain visible for review.</p>
      <button className="btn primary" disabled={save.isPending || policy.isPending}>{save.isPending ? "Saving…" : "Save autonomous validation policy"}</button>
    </> : <p className="empty">Configure a trading account first.</p>}
    {message ? <p className="notice" role="status">{message}</p> : null}
  </form>;
}
