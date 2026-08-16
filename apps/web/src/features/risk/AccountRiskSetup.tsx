"use client";

import { FormEvent, useState } from "react";

import { BrokerAccountIntegration } from "@/features/integrations/BrokerAccountIntegration";

export type AccountSummary = {
  id: string;
  name: string;
  mode: string;
  currency: string;
  starting_balance: string;
  status: string;
  version: number;
  etag: string;
  broker_integration_id?: string | null;
  provider_account_id?: string | null;
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
  onAccountChanged,
  operational = false
}: {
  account: AccountSummary | null;
  onAccountChanged: () => Promise<void>;
  operational?: boolean;
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
        reason: String(form.get("profile-reason") ?? "Initial external loss-rule configuration")
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
        reason: String(form.get("risk-reason") ?? "Initial internal risk-policy configuration")
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

  if (operational) {
    return (
      <div className="governed-workspace">
        <section className="setup-card setup-complete" aria-labelledby="account-risk-current">
          <p className="section-kicker">Authorized control plane</p>
          <h3 id="account-risk-current">Account and risk policy</h3>
          <p>Review current identity and configuration state. Policy replacement requires an MFA-backed owner/admin session, the current ETag, a deliberate confirmation, and a reason. Every prior version remains auditable.</p>
          <dl className="evidence-metrics"><div><dt>Account</dt><dd>{account.name}</dd></div><div><dt>Mode</dt><dd>{account.mode}</dd></div><div><dt>Declared capital</dt><dd>{account.starting_balance} {account.currency}</dd></div><div><dt>Account state</dt><dd>{account.status}</dd></div><div><dt>External profile</dt><dd>{account.prop_profile_configured ? "CONFIGURED" : "MISSING"}</dd></div><div><dt>Internal policy</dt><dd>{account.risk_policy_configured ? "CONFIGURED" : "MISSING"}</dd></div><div><dt>Version / ETag</dt><dd>{account.version} · {account.etag}</dd></div></dl>
        </section>
        <section className="setup-card" aria-labelledby="replace-external-policy">
          <h3 id="replace-external-policy">Replace external loss rules</h3><p><strong>Effect:</strong> Future risk decisions use the new complete rule version. Existing evidence and prior versions are retained.</p>
          <form className="setup-form" onSubmit={savePropProfile}><div className="form-row"><label htmlFor="operational-prop-daily-loss">Daily loss limit<input id="operational-prop-daily-loss" name="prop-daily-loss" min="0.01" required step="0.01" type="number" /></label><label htmlFor="operational-prop-maximum-loss">Maximum loss limit<input id="operational-prop-maximum-loss" name="prop-maximum-loss" min="0.01" required step="0.01" type="number" /></label></div><div className="form-row"><label htmlFor="operational-reset-timezone">Reset time zone<input defaultValue="UTC" id="operational-reset-timezone" name="reset-timezone" required /></label><label htmlFor="operational-reset-time">Reset time<input defaultValue="00:00" id="operational-reset-time" name="reset-time" required type="time" /></label></div><fieldset className="check-grid"><legend>Loss treatment</legend><label><input defaultChecked name="floating-loss-counts" type="checkbox" /> Floating loss counts</label><label><input name="trailing-drawdown" type="checkbox" /> Trailing drawdown</label></fieldset><label htmlFor="profile-reason">Reason for replacement<textarea id="profile-reason" minLength={8} name="profile-reason" required /></label><label className="confirmation-check"><input required type="checkbox" /> I reviewed the effect and intend to replace the complete external profile.</label><button disabled={isSaving} type="submit">{isSaving ? "Recording…" : "Replace external profile"}</button></form>
        </section>
        <section className="setup-card" aria-labelledby="replace-internal-policy">
          <h3 id="replace-internal-policy">Replace internal risk guardrails</h3><p><strong>Effect:</strong> The stricter applicable limit governs future risk decisions. This action never places or changes an order.</p>
          <form className="setup-form" onSubmit={saveRiskPolicy}><div className="form-row"><label htmlFor="operational-risk-per-trade">Maximum risk per trade<input id="operational-risk-per-trade" name="risk-per-trade" min="0.01" required step="0.01" type="number" /></label><label htmlFor="operational-portfolio-risk">Maximum portfolio risk<input id="operational-portfolio-risk" name="portfolio-risk" min="0.01" required step="0.01" type="number" /></label></div><div className="form-row"><label htmlFor="operational-daily-loss">Internal daily loss<input id="operational-daily-loss" name="internal-daily-loss" min="0.01" required step="0.01" type="number" /></label><label htmlFor="operational-drawdown">Internal drawdown<input id="operational-drawdown" name="internal-drawdown" min="0.01" required step="0.01" type="number" /></label></div><div className="form-row"><label htmlFor="operational-prop-buffer">Minimum prop buffer<input defaultValue="0" id="operational-prop-buffer" name="prop-buffer" min="0" required step="0.01" type="number" /></label><label htmlFor="operational-maximum-positions">Maximum positions<select defaultValue="2" id="operational-maximum-positions" name="maximum-positions"><option value="1">1</option><option value="2">2</option></select></label></div><label htmlFor="operational-correlation">Maximum correlated exposure<input defaultValue="1" id="operational-correlation" max="1" min="0" name="correlation-limit" required step="0.01" type="number" /></label><label htmlFor="risk-reason">Reason for replacement<textarea id="risk-reason" minLength={8} name="risk-reason" required /></label><label className="confirmation-check"><input required type="checkbox" /> I reviewed the effect and intend to replace the complete internal policy.</label><button disabled={isSaving} type="submit">{isSaving ? "Recording…" : "Replace internal guardrails"}</button></form>
        </section>
        {message ? <p className="status-message" role="status">{message}</p> : null}
      </div>
    );
  }

  return (
    <section className="setup-card setup-complete" aria-labelledby="verification-heading">
      <p className="section-kicker">Final safety gate</p>
      <h2 id="verification-heading">Awaiting verified account data</h2>
      <p>Your account and risk limits are recorded. TraderX stays in LOCKDOWN until a permitted account integration supplies a verified balance, equity, and position snapshot.</p>
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
      <BrokerAccountIntegration account={account} onAccountChanged={onAccountChanged} />
    </section>
  );
}
