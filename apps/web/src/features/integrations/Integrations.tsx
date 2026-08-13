"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type { AccountSummary } from "@/features/risk/AccountRiskSetup";

type Integration = {
  id: string;
  version: number;
  category: string;
  provider: "OANDA_V20" | "MT5_TERMINAL_BRIDGE";
  status: "HEALTHY" | "DEGRADED" | "FAILED" | "DISABLED";
  credential_hint: string;
};

type ProviderAccount = {
  provider_account_id: string;
  provider: string;
  display_name: string | null;
  currency: string | null;
  account_mode: string;
  verification_status: string;
};

type ApiProblem = { detail?: string; title?: string };

function messageFor(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not complete that integration step.";
}

async function request(path: string, method: "GET" | "POST" | "PUT", body?: object) {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: body
      ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }
      : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  return { response, result: (await response.json().catch(() => ({}))) as ApiProblem };
}

export function Integrations({
  account,
  onAccountChanged
}: {
  account: AccountSummary;
  onAccountChanged: () => Promise<void>;
}) {
  const [provider, setProvider] = useState<Integration["provider"]>("OANDA_V20");
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [accounts, setAccounts] = useState<Record<string, ProviderAccount[]>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const loadIntegrations = useCallback(async () => {
    try {
      const { response, result } = await request("/integrations", "GET");
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      setIntegrations(result as unknown as Integration[]);
    } catch {
      setError("TraderX could not load account integrations.");
    }
  }, []);

  const loadAccounts = useCallback(async (integrationId: string) => {
    const { response, result } = await request(`/integrations/${integrationId}/accounts`, "GET");
    if (!response.ok) throw new Error(messageFor(result));
    setAccounts((current) => ({ ...current, [integrationId]: result as unknown as ProviderAccount[] }));
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadIntegrations);
  }, [loadIntegrations]);

  async function createIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const isOanda = provider === "OANDA_V20";
    const environment = String(form.get("oanda-environment") ?? "PRACTICE");
    if (isOanda && environment === "LIVE" && form.get("live-confirmed") !== "on") {
      setError("Confirm that this is a live OANDA account before continuing.");
      return;
    }
    const configuration = isOanda
      ? { environment, live_confirmed: environment === "LIVE" }
      : {
          bridge_url: form.get("bridge-url"),
          bridge_id: form.get("bridge-id"),
          account_login: form.get("mt5-login"),
          server: form.get("mt5-server")
        };
    const credentials = isOanda
      ? { personal_access_token: form.get("oanda-token") }
      : { bridge_client_secret: form.get("bridge-secret") };

    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request("/integrations", "POST", {
        category: "BROKER",
        provider,
        configuration,
        credentials
      });
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      formElement.reset();
      setMessage("Connection saved. Test it to discover the account that TraderX may verify.");
      await loadIntegrations();
    } catch {
      setError("TraderX could not save this broker connection.");
    } finally {
      setBusy(false);
    }
  }

  async function testIntegration(integration: Integration) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request(`/integrations/${integration.id}/test`, "POST");
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      await Promise.all([loadIntegrations(), loadAccounts(integration.id)]);
      setMessage("Connection verified. Select the returned broker account explicitly.");
    } catch {
      setError("TraderX could not test this broker connection.");
    } finally {
      setBusy(false);
    }
  }

  async function bindAccount(integration: Integration, candidate: ProviderAccount) {
    setBusy(true);
    setError(undefined);
    try {
      const { response, result } = await request(
        `/integrations/${integration.id}/accounts/${encodeURIComponent(candidate.provider_account_id)}/bind`,
        "PUT",
        { account_id: account.id }
      );
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      await onAccountChanged();
      setMessage(`Bound ${candidate.display_name ?? candidate.provider_account_id}. Verify a complete broker snapshot next.`);
    } catch {
      setError("TraderX could not bind this broker account.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyAccount(integration: Integration) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request(`/integrations/${integration.id}/sync`, "POST");
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      await onAccountChanged();
      setMessage("Verified broker snapshot recorded. TraderX recalculated the risk state from current account truth.");
    } catch {
      setError("TraderX could not retrieve a verified broker snapshot.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="integration-panel" aria-labelledby="integrations-heading">
      <header className="integration-heading">
        <div>
          <p className="section-kicker">Step 4 of 4</p>
          <h2 id="integrations-heading">Connect verified account data</h2>
          <p>TraderX reads balances, equity, positions, and deals. It never submits, changes, or closes an order.</p>
        </div>
        <button className="secondary-button" disabled={busy} onClick={() => void loadIntegrations()} type="button">Refresh</button>
      </header>

      <form className="integration-form" onSubmit={createIntegration} aria-label="Connect a broker account">
        <fieldset>
          <legend>Choose a read-only source</legend>
          <label className="provider-choice">
            <input checked={provider === "OANDA_V20"} name="provider" onChange={() => setProvider("OANDA_V20")} type="radio" value="OANDA_V20" />
            <span><strong>OANDA v20</strong><small>Connect a Personal Access Token. New connections start in Practice mode.</small></span>
          </label>
          <label className="provider-choice">
            <input checked={provider === "MT5_TERMINAL_BRIDGE"} name="provider" onChange={() => setProvider("MT5_TERMINAL_BRIDGE")} type="radio" value="MT5_TERMINAL_BRIDGE" />
            <span><strong>MetaTrader 5 bridge</strong><small>Connect your registered HTTPS bridge; the investor password stays on that bridge.</small></span>
          </label>
        </fieldset>

        {provider === "OANDA_V20" ? (
          <div className="integration-fields">
            <label htmlFor="oanda-environment">OANDA environment<select defaultValue="PRACTICE" id="oanda-environment" name="oanda-environment"><option value="PRACTICE">Practice (recommended)</option><option value="LIVE">Live</option></select></label>
            <label htmlFor="oanda-token">Personal Access Token<input autoComplete="off" id="oanda-token" name="oanda-token" required type="password" /></label>
            <p className="field-hint">This token is encrypted and write-only. TraderX only permits reviewed read requests.</p>
            <label className="confirmation-check"><input name="live-confirmed" type="checkbox" /> I confirm that selecting Live connects real account data, while TraderX remains decision-support only.</label>
          </div>
        ) : (
          <div className="integration-fields">
            <label htmlFor="bridge-url">Bridge URL<input id="bridge-url" name="bridge-url" placeholder="https://mt5-bridge.example.com" required type="url" /></label>
            <div className="form-row"><label htmlFor="bridge-id">Bridge identity<input id="bridge-id" name="bridge-id" required /></label><label htmlFor="mt5-login">MT5 account login<input id="mt5-login" name="mt5-login" required /></label></div>
            <label htmlFor="mt5-server">Broker server<input id="mt5-server" name="mt5-server" placeholder="Broker-Demo" required /></label>
            <label htmlFor="bridge-secret">Bridge client credential<input autoComplete="off" id="bridge-secret" name="bridge-secret" required type="password" /></label>
            <p className="field-hint">Do not enter an MT5 trading or investor password here. The isolated bridge stores the investor password and must prove trading is disabled.</p>
          </div>
        )}
        <button disabled={busy} type="submit">{busy ? "Saving…" : "Save read-only connection"}</button>
      </form>

      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}

      <div className="integration-list" aria-live="polite">
        {integrations.length === 0 ? <p className="empty-integrations">No broker connection has been saved yet.</p> : integrations.map((integration) => (
          <article className="integration-card" key={integration.id}>
            <div><p className="section-kicker">{integration.provider === "OANDA_V20" ? "OANDA v20" : "MetaTrader 5 bridge"}</p><h3>{integration.status.replaceAll("_", " ")}</h3><p>{integration.credential_hint}</p></div>
            <div className="integration-actions">
              <button disabled={busy} onClick={() => void testIntegration(integration)} type="button">Test & discover accounts</button>
              {account.broker_integration_id === integration.id ? <button className="secondary-button" disabled={busy} onClick={() => void verifyAccount(integration)} type="button">Verify account data</button> : null}
            </div>
            {(accounts[integration.id] ?? []).length > 0 ? <div className="discovered-accounts"><h4>Returned accounts</h4>{accounts[integration.id].map((candidate) => <div className="provider-account" key={candidate.provider_account_id}><span><strong>{candidate.display_name ?? candidate.provider_account_id}</strong><small>{candidate.provider_account_id} · {candidate.currency ?? "currency unavailable"} · {candidate.account_mode}</small></span><button disabled={busy || account.broker_integration_id === integration.id} onClick={() => void bindAccount(integration, candidate)} type="button">{account.broker_integration_id === integration.id ? "Bound" : "Bind this account"}</button></div>)}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
