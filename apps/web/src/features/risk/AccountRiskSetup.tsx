"use client";

import { FormEvent, useState } from "react";

export type AccountSummary = {
  id: string;
  name: string;
  mode: string;
  currency: string;
  starting_balance: string;
  status: string;
  version: number;
  etag: string;
  prop_profile_configured: boolean;
  risk_policy_configured: boolean;
};

type ApiProblem = { detail?: string; title?: string };

function problemMessage(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not save this configuration. Please try again.";
}

async function send(path: string, body: object, headers: Record<string, string> = {}) {
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID(), ...headers },
    body: JSON.stringify(body)
  });
  const result = (await response.json().catch(() => ({}))) as ApiProblem;
  return { response, result };
}

async function replace(path: string, body: object, etag: string) {
  const response = await fetch(`/api/v1${path}`, {
    method: "PUT",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
      "If-Match": etag
    },
    body: JSON.stringify(body)
  });
  const result = (await response.json().catch(() => ({}))) as ApiProblem;
  return { response, result };
}

export function AccountRiskSetup({
  account,
  onAccountChanged
}: {
  account: AccountSummary | null;
  onAccountChanged: () => Promise<void>;
}) {
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string>();

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setMessage(undefined);
    try {
      const { response, result } = await send("/accounts", {
        name: form.get("account-name"),
        currency: form.get("currency"),
        starting_balance: form.get("starting-balance"),
        mode: form.get("mode")
      });
      if (!response.ok) {
        setMessage(problemMessage(result));
        return;
      }
      setMessage("Account identity recorded. Next, enter the external loss rules that govern it.");
      await onAccountChanged();
    } catch {
      setMessage("TraderX could not reach the account service. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  async function savePropProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setMessage(undefined);
    try {
      const { response, result } = await replace(`/accounts/${account.id}/prop-profile`, {
        daily_loss_limit: form.get("prop-daily-loss"),
        maximum_loss_limit: form.get("prop-maximum-loss"),
        trailing_drawdown: form.get("trailing-drawdown") === "on",
        floating_loss_counts: form.get("floating-loss-counts") === "on",
        reset_timezone: form.get("reset-timezone"),
        reset_time: form.get("reset-time"),
        reason: "Initial external loss-rule configuration"
      }, account.etag);
      if (!response.ok) {
        setMessage(problemMessage(result));
        return;
      }
      setMessage("External loss rules recorded. Continue with your internal risk guardrails.");
      await onAccountChanged();
    } catch {
      setMessage("TraderX could not save the external rules. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveRiskPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setMessage(undefined);
    try {
      const { response, result } = await replace(`/accounts/${account.id}/risk-policy`, {
        maximum_risk_per_trade: form.get("risk-per-trade"),
        maximum_portfolio_risk: form.get("portfolio-risk"),
        internal_daily_loss_limit: form.get("internal-daily-loss"),
        internal_drawdown_limit: form.get("internal-drawdown"),
        minimum_prop_buffer: form.get("prop-buffer"),
        maximum_positions: Number(form.get("maximum-positions")),
        correlation_limit: form.get("correlation-limit"),
        reason: "Initial internal risk-policy configuration"
      }, account.etag);
      if (!response.ok) {
        setMessage(problemMessage(result));
        return;
      }
      setMessage("Internal guardrails recorded. TraderX will remain locked until verified account data arrives.");
      await onAccountChanged();
    } catch {
      setMessage("TraderX could not save the internal guardrails. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!account) {
    return (
      <section className="setup-card" aria-labelledby="account-setup-heading">
        <p className="section-kicker">Step 1 of 3</p>
        <h2 id="account-setup-heading">Register the primary account</h2>
        <p>Record the account identity and its declared starting balance. This does not connect a broker or enable recommendations.</p>
        <form className="setup-form" onSubmit={createAccount} aria-label="Primary account setup">
          <label htmlFor="account-name">Account name</label>
          <input autoComplete="off" id="account-name" name="account-name" placeholder="e.g. Apex evaluation 100K" required />
          <div className="form-row">
            <label htmlFor="currency">Currency<input id="currency" name="currency" defaultValue="USD" maxLength={3} minLength={3} required /></label>
            <label htmlFor="starting-balance">Starting balance<input id="starting-balance" name="starting-balance" inputMode="decimal" min="0.01" placeholder="100000" required type="number" step="0.01" /></label>
          </div>
          <label htmlFor="mode">Account mode</label>
          <select defaultValue="LIVE" id="mode" name="mode"><option value="LIVE">Live / evaluation</option><option value="PAPER">Paper</option><option value="DEMO">Demo</option></select>
          <button disabled={isSaving} type="submit">{isSaving ? "Recording…" : "Record account identity"}</button>
        </form>
        {message ? <p className="status-message" data-tone="error" role="alert">{message}</p> : null}
      </section>
    );
  }

  if (!account.prop_profile_configured) {
    return (
      <section className="setup-card" aria-labelledby="prop-profile-heading">
        <p className="section-kicker">Step 2 of 3</p>
        <h2 id="prop-profile-heading">Record external loss rules</h2>
        <p>Enter the limits that apply to <strong>{account.name}</strong>. TraderX uses the stricter rule whenever an internal limit also applies.</p>
        <form className="setup-form" onSubmit={savePropProfile} aria-label="External loss-rule setup">
          <div className="form-row">
            <label htmlFor="prop-daily-loss">Daily loss limit<input id="prop-daily-loss" name="prop-daily-loss" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label>
            <label htmlFor="prop-maximum-loss">Maximum loss limit<input id="prop-maximum-loss" name="prop-maximum-loss" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label>
          </div>
          <div className="form-row">
            <label htmlFor="reset-timezone">Daily reset time zone<input defaultValue="UTC" id="reset-timezone" name="reset-timezone" required /></label>
            <label htmlFor="reset-time">Daily reset time<input defaultValue="00:00" id="reset-time" name="reset-time" required type="time" /></label>
          </div>
          <fieldset className="check-grid"><legend>Loss treatment</legend><label><input defaultChecked name="floating-loss-counts" type="checkbox" /> Floating loss counts toward the limit</label><label><input name="trailing-drawdown" type="checkbox" /> Drawdown is trailing</label></fieldset>
          <button disabled={isSaving} type="submit">{isSaving ? "Saving…" : "Save external loss rules"}</button>
        </form>
        {message ? <p className="status-message" data-tone="error" role="alert">{message}</p> : null}
      </section>
    );
  }

  if (!account.risk_policy_configured) {
    return (
      <section className="setup-card" aria-labelledby="internal-risk-heading">
        <p className="section-kicker">Step 3 of 3</p>
        <h2 id="internal-risk-heading">Set internal risk guardrails</h2>
        <p>These limits are deliberate constraints. They never expand the external rules you entered in the previous step.</p>
        <form className="setup-form" onSubmit={saveRiskPolicy} aria-label="Internal risk-policy setup">
          <div className="form-row"><label htmlFor="risk-per-trade">Maximum risk per trade<input id="risk-per-trade" name="risk-per-trade" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label><label htmlFor="portfolio-risk">Maximum portfolio risk<input id="portfolio-risk" name="portfolio-risk" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label></div>
          <div className="form-row"><label htmlFor="internal-daily-loss">Internal daily loss limit<input id="internal-daily-loss" name="internal-daily-loss" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label><label htmlFor="internal-drawdown">Internal drawdown limit<input id="internal-drawdown" name="internal-drawdown" inputMode="decimal" min="0.01" required type="number" step="0.01" /></label></div>
          <div className="form-row"><label htmlFor="prop-buffer">Minimum prop safety buffer<input defaultValue="0" id="prop-buffer" name="prop-buffer" inputMode="decimal" min="0" required type="number" step="0.01" /></label><label htmlFor="maximum-positions">Maximum positions<select defaultValue="2" id="maximum-positions" name="maximum-positions"><option value="1">1</option><option value="2">2</option></select></label></div>
          <label htmlFor="correlation-limit">Maximum correlated exposure (0–1)<input defaultValue="1" id="correlation-limit" name="correlation-limit" min="0" max="1" required type="number" step="0.01" /></label>
          <button disabled={isSaving} type="submit">{isSaving ? "Saving…" : "Save internal guardrails"}</button>
        </form>
        {message ? <p className="status-message" data-tone="error" role="alert">{message}</p> : null}
      </section>
    );
  }

  return (
    <section className="setup-card setup-complete" aria-labelledby="verification-heading">
      <p className="section-kicker">Final safety gate</p>
      <h2 id="verification-heading">Awaiting verified account data</h2>
      <p>Your account and risk limits are recorded. TraderX stays in LOCKDOWN until a permitted account integration supplies a verified balance, equity, and position snapshot.</p>
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
    </section>
  );
}
