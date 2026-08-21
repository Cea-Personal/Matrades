"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type { AccountSummary } from "@/features/risk/AccountRiskSetup";

type Integration = {
  id: string;
  version: number;
  category: string;
  provider: "MT5_TERMINAL_BRIDGE";
  name: string;
  mt5_account_login: string;
  mt5_server: string;
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

type ManagedMt5Enrollment = Integration & {
  enrollment: { agent_id: string; code: string; expires_at: string };
};

type ProviderDefinition = {
  provider: string;
  category: string;
  configuration_fields: string[];
  credential_fields: string[];
  asset_categories: string[];
  permitted_models: string[];
  licensing_notice: string;
  retention_posture: string;
  entitlement_required: boolean;
  verification_only: boolean;
};

type ResearchIntegration = {
  id: string;
  version: number;
  name: string;
  category: string;
  provider: string;
  state: string;
  credential: "WRITE_ONLY";
  credential_status: string;
  entitlement_status: string;
  catalogue_revision: string;
  retention_posture: string;
};

type ExperimentalCalendarEvent = {
  id: string;
  title: string;
  event_type: string;
  importance: string;
  scheduled_at: string;
  official_url: string;
};

type LiteLlmModel = { id: string; alias: string };

const providerNames: Record<string, string> = {
  TWELVE_DATA: "Twelve Data",
  COINBASE_EXCHANGE: "Coinbase Exchange",
  LITELLM_PROXY: "LiteLLM Gateway"
};

const manuallyConnectableProviders = new Set([
  "TWELVE_DATA", "COINBASE_EXCHANGE", "LITELLM_PROXY"
]);

function messageFor(result: ApiProblem): string {
  return result.detail ?? result.title ?? "TraderX could not complete that integration step.";
}

async function request(path: string, method: "GET" | "POST" | "PUT" | "DELETE", body?: object) {
  const mutationHeaders = method === "GET" ? undefined : { "Idempotency-Key": crypto.randomUUID() };
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: body ? { ...mutationHeaders, "Content-Type": "application/json" } : mutationHeaders,
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
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [accounts, setAccounts] = useState<Record<string, ProviderAccount[]>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const [mt5Enrollment, setMt5Enrollment] = useState<ManagedMt5Enrollment>();
  const [showNewConnection, setShowNewConnection] = useState(false);
  const [removeConfirmationId, setRemoveConfirmationId] = useState<string>();
  const [siteOrigin] = useState(() => typeof window === "undefined" ? "" : window.location.origin);
  const localDevelopmentOrigin = siteOrigin.includes("localhost") || siteOrigin.includes("127.0.0.1");
  const mt5SiteOrigin = localDevelopmentOrigin ? "https://127.0.0.1:3000" : siteOrigin;

  const loadIntegrations = useCallback(async () => {
    try {
      const { response, result } = await request("/integrations", "GET");
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      setIntegrations(result as unknown as Integration[]);
      setError(undefined);
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
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request("/integrations/mt5/enrollments", "POST", {
        account_login: form.get("mt5-login"),
        server: form.get("mt5-server")
      });
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      formElement.reset();
      setMt5Enrollment(result as unknown as ManagedMt5Enrollment);
      setShowNewConnection(false);
      setMessage("Your MT5 setup code is ready. Install the TraderX read-only Expert Advisor in your MT5 terminal.");
      await loadIntegrations();
    } catch {
      setError("TraderX could not save this broker connection.");
    } finally {
      setBusy(false);
    }
  }

  async function renewMt5Enrollment(integration: Integration) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request(`/integrations/${integration.id}/mt5/enrollment`, "POST", {});
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      setMt5Enrollment(result as unknown as ManagedMt5Enrollment);
      setMessage("A new MT5 setup code is ready. Any earlier bridge credential was revoked.");
      await loadIntegrations();
    } catch {
      setError("TraderX could not create a new MT5 setup code.");
    } finally {
      setBusy(false);
    }
  }

  async function copyMt5Code() {
    if (!mt5Enrollment) return;
    try {
      await navigator.clipboard.writeText(mt5Enrollment.enrollment.code);
      setMessage("MT5 setup code copied. Paste it into the TraderX Expert Advisor inputs in MT5.");
    } catch {
      setError("Copying was blocked by this browser. Select and copy the setup code manually.");
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

  async function setIntegrationEnabled(integration: Integration, enabled: boolean) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}/state`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "If-Match": `"integration-${integration.version}"`, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ enabled, reason: enabled ? "Reconnect this approved read-only MT5 integration" : "Temporarily disable this MT5 integration" })
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      await Promise.all([loadIntegrations(), onAccountChanged()]);
      setMessage(enabled ? "Integration enabled in verification-required state. Reconnect and verify the account snapshot." : "Integration disabled. Its account data is no longer authoritative and TraderX remains fail closed.");
    } catch { setError("TraderX could not change the integration state."); }
    finally { setBusy(false); }
  }

  async function removeMt5Integration(integration: Integration) {
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const { response, result } = await request(`/integrations/${integration.id}`, "DELETE");
      if (!response.ok) {
        setError(messageFor(result));
        return;
      }
      if (mt5Enrollment?.id === integration.id) setMt5Enrollment(undefined);
      setAccounts((current) => {
        const { [integration.id]: removed, ...remaining } = current;
        return remaining;
      });
      setRemoveConfirmationId(undefined);
      await Promise.all([loadIntegrations(), onAccountChanged()]);
      setMessage(`Removed MT5 account ${integration.mt5_account_login}. Its bridge credential was revoked.`);
    } catch {
      setError("TraderX could not remove this MT5 account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="integration-panel" aria-labelledby="integrations-heading">
      <header className="integration-heading">
        <div>
          <p className="section-kicker">Step 4 of 4</p>
          <h2 id="integrations-heading">Verified account data</h2>
          <p>Connect the read-only MT5 bridge to verify balance, equity, positions, and deals. TraderX never submits, changes, or closes an order.</p>
        </div>
        <button className="secondary-button" disabled={busy} onClick={() => void loadIntegrations()} type="button">Refresh</button>
      </header>

      {integrations.length === 0 || showNewConnection ? <form className="integration-form" onSubmit={createIntegration} aria-label="Connect a broker account">
        <div className="integration-fields">
          <p className="field-hint"><strong>MetaTrader 5 only.</strong> TraderX creates a one-time setup code for a read-only Expert Advisor that runs inside MT5 on your Mac or Windows computer.</p>
          <label htmlFor="mt5-login">MT5 account login<input id="mt5-login" name="mt5-login" required /></label>
          <label htmlFor="mt5-server">Broker server<input id="mt5-server" name="mt5-server" placeholder="Broker-Demo" required /></label>
          <p className="field-hint">You will receive a one-time code for TraderX’s read-only MT5 Expert Advisor. Sign into MT5 with the investor password; it never enters TraderX.</p>
        </div>
        <div className="integration-form-actions"><button disabled={busy} type="submit">{busy ? "Saving…" : "Create MT5 setup code"}</button>{integrations.length > 0 ? <button className="secondary-button" disabled={busy} onClick={() => setShowNewConnection(false)} type="button">Cancel</button> : null}</div>
      </form> : null}

      {mt5Enrollment ? <section className="mt5-setup-code" aria-labelledby="mt5-setup-heading">
        <div><p className="section-kicker">MT5 setup</p><h3 id="mt5-setup-heading">Install this in your MT5 terminal</h3><p className="mt5-account-reference"><strong>This setup code is for MT5 account {mt5Enrollment.mt5_account_login}</strong> on {mt5Enrollment.mt5_server}.</p><p>Works in MetaTrader 5 for macOS and Windows. Sign into the intended account with its investor password, then add the TraderX Read-only Bridge Expert Advisor to any open chart.</p></div>
        <ol className="mt5-setup-steps"><li><a download href="/mt5-bridge/TraderXReadOnlyBridge.mq5">Download the TraderX Read-only Bridge EA</a>, then open it in MetaEditor and compile it.</li><li>In MT5, choose <strong>Tools → Options → Expert Advisors</strong> and add <code>{mt5SiteOrigin || "your TraderX HTTPS origin"}</code> to “Allow WebRequest for listed URL”.</li><li>Attach <strong>TraderXReadOnlyBridge</strong> to a chart, set the three inputs below, and leave Auto Trading disabled.</li></ol>
        <code className="mt5-launch-command">{mt5SiteOrigin ? `TraderXApiUrl: ${mt5SiteOrigin}/api/v1\nAgentId: ${mt5Enrollment.enrollment.agent_id}\nEnrollmentCode: paste the one-time code below` : "Preparing MT5 Expert Advisor inputs…"}</code>
        <div className="setup-code-value"><code>{mt5Enrollment.enrollment.code}</code><button className="secondary-button" onClick={() => void copyMt5Code()} type="button">Copy code</button></div>
        <p className="field-hint">Code expires {new Date(mt5Enrollment.enrollment.expires_at).toLocaleString()}. The EA runs only while MT5 is connected and shows both account and terminal trading as disabled. No bridge URL, identity, or bridge credential is required.</p>
        {localDevelopmentOrigin ? <p className="mt5-local-warning">For local MT5 on macOS, use <code>https://127.0.0.1:3000</code> rather than <code>localhost</code>. Local HTTPS still uses TraderX’s development certificate, so deploy to a publicly trusted HTTPS domain or explicitly trust the local Caddy certificate inside the MT5 Wine environment.</p> : null}
        <a href="/mt5-bridge" target="_blank">Open MT5 bridge deployment guide</a>
      </section> : null}

      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}

      <div className="integration-list" aria-live="polite">
        {integrations.length === 0 ? <p className="empty-integrations">No broker connection has been saved yet.</p> : integrations.map((integration) => (
          <article className="integration-card" key={integration.id}>
            <div><p className="section-kicker">MetaTrader 5 bridge</p><h3>MT5 account {integration.mt5_account_login}</h3><p className="mt5-account-reference"><strong>Broker server:</strong> {integration.mt5_server}</p><p>{integration.status.replaceAll("_", " ")} · {integration.credential_hint}</p></div>
            <div className="integration-actions">
              {integration.status === "HEALTHY" ? <button disabled={busy} onClick={() => void testIntegration(integration)} type="button">Test & discover accounts</button> : null}<button className={integration.status === "HEALTHY" ? "secondary-button" : undefined} disabled={busy} onClick={() => void renewMt5Enrollment(integration)} type="button">{integration.status === "HEALTHY" ? "Reconnect MT5 bridge" : "Create setup code for this account"}</button>
              {account.broker_integration_id === integration.id ? <button className="secondary-button" disabled={busy} onClick={() => void verifyAccount(integration)} type="button">Verify account data</button> : null}
              <button className="secondary-button" disabled={busy} onClick={() => void setIntegrationEnabled(integration, integration.status === "DISABLED")} type="button">{integration.status === "DISABLED" ? "Enable integration" : "Disable integration"}</button>
              {removeConfirmationId === integration.id ? <><button className="danger-button" disabled={busy} onClick={() => void removeMt5Integration(integration)} type="button">Confirm remove MT5 account {integration.mt5_account_login}</button><button className="secondary-button" disabled={busy} onClick={() => setRemoveConfirmationId(undefined)} type="button">Cancel</button></> : <button className="danger-button" disabled={busy} onClick={() => setRemoveConfirmationId(integration.id)} type="button">Remove this MT5 account</button>}
            </div>
            {removeConfirmationId === integration.id ? <p className="remove-integration-warning">Removing this account revokes its EA credential. If it is bound to TraderX, it will be unbound and TraderX will remain in LOCKDOWN until another verified account is connected.</p> : null}
            {(accounts[integration.id] ?? []).length > 0 ? <div className="discovered-accounts"><h4>Returned accounts</h4>{accounts[integration.id].map((candidate) => <div className="provider-account" key={candidate.provider_account_id}><span><strong>{candidate.display_name ?? candidate.provider_account_id}</strong><small>{candidate.provider_account_id} · {candidate.currency ?? "currency unavailable"} · {candidate.account_mode}</small></span><button disabled={busy || account.broker_integration_id === integration.id} onClick={() => void bindAccount(integration, candidate)} type="button">{account.broker_integration_id === integration.id ? "Bound" : "Bind this account"}</button></div>)}</div> : null}
          </article>
        ))}
      </div>
      {integrations.length > 0 && !showNewConnection ? <button className="secondary-button" disabled={busy} onClick={() => setShowNewConnection(true)} type="button">Connect a different MT5 account</button> : null}
      <ResearchProviders />
    </section>
  );
}

function ResearchProviders() {
  const [catalogue, setCatalogue] = useState<ProviderDefinition[]>([]);
  const [configured, setConfigured] = useState<ResearchIntegration[]>([]);
  const [selected, setSelected] = useState("COINBASE_EXCHANGE");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const [experimentalEvents, setExperimentalEvents] = useState<ExperimentalCalendarEvent[]>([]);
  const [experimentalImportStatus, setExperimentalImportStatus] = useState<string>();
  const [experimentalCacheState, setExperimentalCacheState] = useState<
    "LOADING" | "EMPTY" | "READY" | "UNAVAILABLE" | "IMPORT_QUEUED"
  >("LOADING");
  const [liteLlmModels, setLiteLlmModels] = useState<LiteLlmModel[]>([]);
  const [liteLlmGatewayState, setLiteLlmGatewayState] = useState<"LOADING" | "HEALTHY" | "UNAVAILABLE">("LOADING");

  const loadLiteLlmModels = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/integrations/litellm/models", { credentials: "same-origin" });
      if (!response.ok) throw new Error("gateway unavailable");
      const payload = await response.json() as { gateway_state?: "HEALTHY" | "UNAVAILABLE"; items?: LiteLlmModel[] };
      setLiteLlmModels(payload.items ?? []);
      setLiteLlmGatewayState(payload.gateway_state === "HEALTHY" ? "HEALTHY" : "UNAVAILABLE");
    } catch {
      setLiteLlmModels([]);
      setLiteLlmGatewayState("UNAVAILABLE");
    }
  }, []);

  const loadExperimentalEvents = useCallback(async () => {
    setExperimentalCacheState("LOADING");
    try {
      const response = await fetch(
        "/api/v1/economic-calendar/experimental/forex-factory/cache?limit=100&offset=0",
        { credentials: "same-origin" }
      );
      if (!response.ok) throw new Error("experimental cache unavailable");
      const payload = await response.json() as { items: ExperimentalCalendarEvent[] };
      setExperimentalEvents(payload.items);
      setExperimentalCacheState(payload.items.length ? "READY" : "EMPTY");
    } catch {
      setExperimentalEvents([]);
      setExperimentalCacheState("UNAVAILABLE");
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const [catalogueResponse, configuredResponse] = await Promise.all([
        fetch("/api/v1/integrations/providers", { credentials: "same-origin" }),
        fetch("/api/v1/integrations/non-broker", { credentials: "same-origin" })
      ]);
      if (!catalogueResponse.ok || !configuredResponse.ok) throw new Error("unavailable");
      const all = (await catalogueResponse.json() as { items: ProviderDefinition[] }).items;
      setCatalogue(all.filter((item) => manuallyConnectableProviders.has(item.provider) && !item.verification_only));
      setConfigured((await configuredResponse.json() as { items: ResearchIntegration[] }).items.filter((item) => providerNames[item.provider]));
      setError(undefined);
    } catch { setError("TraderX could not load the reviewed research-provider catalogue."); }
  }, []);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  useEffect(() => {
    void loadExperimentalEvents();
  }, [loadExperimentalEvents]);
  const definition = catalogue.find((item) => item.provider === selected);
  const liteLlmConnection = configured.find((item) => item.provider === "LITELLM_PROXY");
  useEffect(() => {
    if (liteLlmConnection) void loadLiteLlmModels();
    else {
      setLiteLlmModels([]);
      setLiteLlmGatewayState("UNAVAILABLE");
    }
  }, [liteLlmConnection, loadLiteLlmModels]);
  const healthyProviders = catalogue.filter((item) =>
    configured.some(
      (integration) => integration.provider === item.provider && integration.state === "HEALTHY"
    )
  );

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!definition) return;
    const form = new FormData(event.currentTarget);
    const configuration = Object.fromEntries(definition.configuration_fields.map((field) => [field, form.get(`configuration-${field}`)]));
    const credentials = Object.fromEntries(definition.credential_fields.map((field) => [field, form.get(`credential-${field}`)]));
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/integrations/non-broker", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ provider: definition.provider, name: String(form.get("provider-name")), configuration, credentials, capabilities: [definition.category === "LLM" ? "LLM_ANALYSIS" : definition.category === "ECONOMIC_CALENDAR" ? "ECONOMIC_CALENDAR_READ" : "MARKET_DATA_READ"], official_source: true, licensing_accepted: form.get("licensing-accepted") === "on", retention_accepted: form.get("retention-accepted") === "on", reason: form.get("provider-reason") })
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`${providerNames[definition.provider]} was saved with write-only credentials. Test and qualify it before research use.`);
      await load();
    } catch { setError("TraderX could not connect this reviewed provider."); }
    finally { setBusy(false); }
  }

  async function configureLiteLlmModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/integrations/litellm/models", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          alias: form.get("litellm-alias"),
          provider_model: form.get("litellm-provider-model"),
          provider_api_key: form.get("litellm-provider-api-key"),
          provider_api_base: form.get("litellm-provider-api-base") || undefined,
          reason: form.get("litellm-reason")
        })
      });
      const result = await response.json() as ApiProblem & { alias?: string };
      if (!response.ok) { setError(messageFor(result)); return; }
      formElement.reset();
      setMessage(`LiteLLM model ${result.alias ?? "alias"} was saved. Its upstream API key remains write-only.`);
      await loadLiteLlmModels();
    } catch { setError("TraderX could not save the LiteLLM model configuration."); }
    finally { setBusy(false); }
  }

  async function removeLiteLlmModel(model: LiteLlmModel) {
    if (!window.confirm(`Remove LiteLLM model alias “${model.alias}”? This removes its provider configuration from the private gateway.`)) return;
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/litellm/models/${encodeURIComponent(model.id)}`, {
        method: "DELETE", credentials: "same-origin", headers: { "Idempotency-Key": crypto.randomUUID() }
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`LiteLLM model ${model.alias} was removed from the private gateway.`);
      await loadLiteLlmModels();
    } catch { setError("TraderX could not remove the LiteLLM model alias."); }
    finally { setBusy(false); }
  }

  async function importExperimentalCalendar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const sources = String(form.get("scraper-sources") ?? "")
      .split(",")
      .map((source) => source.trim())
      .filter(Boolean);
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/economic-calendar/experimental/forex-factory/import", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          acknowledge_non_production: true,
          start_date: form.get("scraper-start-date"),
          end_date: form.get("scraper-end-date"),
          sources,
          limit: Number(form.get("scraper-limit")),
          offset: Number(form.get("scraper-offset"))
        })
      });
      const result = await response.json() as ApiProblem & { task_id?: string };
      if (!response.ok) { setError(messageFor(result)); return; }
      setExperimentalCacheState("IMPORT_QUEUED");
      setExperimentalImportStatus("Queued — waiting for the experimental worker.");
      setMessage("Experimental scraper import queued. Its events remain excluded from calendar coverage and all recommendation gates.");
      if (result.task_id) void pollExperimentalImport(result.task_id);
    } catch { setError("TraderX could not queue the experimental calendar import. Start the experimental scraper profile first."); }
    finally { setBusy(false); }
  }

  async function pollExperimentalImport(taskId: string, attempt = 0): Promise<void> {
    try {
      const response = await fetch(
        `/api/v1/economic-calendar/experimental/forex-factory/imports/${taskId}`,
        { credentials: "same-origin" }
      );
      const payload = await response.json() as {
        state?: string;
        result?: { status?: string; events?: number; detail?: string };
      } & ApiProblem;
      if (!response.ok) { setExperimentalImportStatus(messageFor(payload)); return; }
      if (payload.state === "SUCCESS") {
        if (payload.result?.status === "IMPORTED_EXPERIMENTAL_NOT_FOR_GATING") {
          setExperimentalImportStatus(`Import completed — ${payload.result.events ?? 0} event(s) stored in the experimental cache.`);
          await loadExperimentalEvents();
        } else {
          setExperimentalImportStatus(
            `Import did not store results: ${payload.result?.detail ?? payload.result?.status ?? "unknown experimental worker result"}.`
          );
          setExperimentalCacheState("EMPTY");
        }
        return;
      }
      if (payload.state === "FAILURE") {
        setExperimentalImportStatus("Experimental worker failed before it could import data. Check its Docker logs.");
        return;
      }
      setExperimentalImportStatus(`${payload.state ?? "PENDING"} — waiting for the experimental worker.`);
      if (attempt < 15) window.setTimeout(() => { void pollExperimentalImport(taskId, attempt + 1); }, 2000);
    } catch {
      setExperimentalImportStatus("TraderX could not read the experimental import status.");
    }
  }

  async function lifecycle(integration: ResearchIntegration, action: "ENABLE" | "DISABLE" | "RECONNECT") {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}/non-broker/state`, {
        method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "If-Match": `"integration-${integration.version}"`, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ action, reason: `${action.toLowerCase()} reviewed research provider` })
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`${providerNames[integration.provider]} is ${action === "DISABLE" ? "disabled" : "verification required"}.`);
      await load();
    } catch { setError("TraderX could not change the provider lifecycle."); }
    finally { setBusy(false); }
  }

  async function refreshExperimentalCache() {
    setBusy(true); setError(undefined);
    await loadExperimentalEvents();
    setBusy(false);
  }

  async function testProvider(integration: ResearchIntegration) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}/test`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Idempotency-Key": crypto.randomUUID() }
      });
      const result = await response.json() as ApiProblem & { id?: string };
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`Qualification job ${result.id ?? ""} was queued. TraderX will test only the reviewed endpoint and keep credentials redacted.`);
      await load();
    } catch { setError("TraderX could not queue the provider qualification test."); }
    finally { setBusy(false); }
  }

  async function rotateCredential(event: FormEvent<HTMLFormElement>, integration: ResearchIntegration) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const provider = catalogue.find((item) => item.provider === integration.provider);
    if (!provider) return;
    const form = new FormData(formElement);
    const credentials = Object.fromEntries(provider.credential_fields.map((field) => [field, form.get(`rotate-${field}`)]));
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}/credentials/rotate`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "If-Match": `"integration-${integration.version}"`, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ credentials })
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      formElement.reset();
      setMessage(`${providerNames[integration.provider]} credential rotated. Run the provider test before enabling research use.`);
      await load();
    } catch { setError("TraderX could not rotate the write-only credential."); }
    finally { setBusy(false); }
  }

  async function declareEntitlement(event: FormEvent<HTMLFormElement>, integration: ResearchIntegration) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}/entitlement`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "If-Match": `"integration-${integration.version}"`, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ confirmation: "CONFIRM_ENTITLEMENT", evidence_reference: form.get("entitlement-reference"), reason: form.get("entitlement-reason") })
      });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`${providerNames[integration.provider]} entitlement evidence recorded. A successful live provider test is still required.`);
      await load();
    } catch { setError("TraderX could not record the entitlement evidence."); }
    finally { setBusy(false); }
  }

  async function removeProvider(integration: ResearchIntegration) {
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch(`/api/v1/integrations/${integration.id}`, { method: "DELETE", credentials: "same-origin", headers: { "If-Match": `"integration-${integration.version}"`, "Idempotency-Key": crypto.randomUUID() } });
      const result = await response.json() as ApiProblem;
      if (!response.ok) { setError(messageFor(result)); return; }
      setMessage(`${providerNames[integration.provider]} was removed and its credential revoked.`);
      await load();
    } catch { setError("TraderX could not remove the provider."); }
    finally { setBusy(false); }
  }

  return (
    <section aria-labelledby="research-providers">
      <p className="section-kicker">Provider connections</p>
      <h2 id="research-providers">Reviewed research providers</h2>
      <p>Configure specialist market data and advisory models here in the current Integrations workspace. Credentials are write-only. Licensing and retention must be reviewed before connection.</p>
      {liteLlmConnection ? <section className="setup-card" aria-labelledby="litellm-model-heading">
        <p className="section-kicker">LiteLLM gateway connection</p>
        <h3 id="litellm-model-heading">Configure models for {liteLlmConnection.name}</h3>
        <p>Add the model alias and upstream provider credential here. TraderX sends this only to the private LiteLLM gateway; it never writes provider keys into YAML or returns them to the browser.</p>
        {liteLlmGatewayState === "LOADING" ? <p className="field-hint">Checking the private LiteLLM gateway…</p> : null}
        {liteLlmGatewayState === "UNAVAILABLE" ? <p className="field-hint">The private gateway is not available yet. Start the <code>llm-gateway</code> Docker profile with <code>LITELLM_MASTER_KEY</code>, then refresh this page.</p> : null}
        <form className="setup-form" onSubmit={configureLiteLlmModel}>
          <div className="form-row">
            <label>TraderX model alias<input name="litellm-alias" pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}" placeholder="research-fast" required /></label>
            <label>Provider model ID<input name="litellm-provider-model" pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}" placeholder="openai/gpt-4.1-mini" required /></label>
          </div>
          <label>Provider API key<input autoComplete="new-password" name="litellm-provider-api-key" required type="password" /></label>
          <label>Provider API base (optional)<input name="litellm-provider-api-base" placeholder="https://api.example.com/v1" type="url" /></label>
          <label>Reason<textarea minLength={8} name="litellm-reason" required /></label>
          <button disabled={busy || liteLlmGatewayState !== "HEALTHY"} type="submit">Save LiteLLM model</button>
        </form>
        <div className="integration-form-actions"><h4>Configured aliases</h4><button className="secondary-button" disabled={busy} onClick={() => void loadLiteLlmModels()} type="button">Refresh models</button></div>
        {liteLlmGatewayState === "HEALTHY" && liteLlmModels.length === 0 ? <p className="empty-state">No model aliases configured yet.</p> : null}
        {liteLlmModels.length ? <div className="integration-list">{liteLlmModels.map((model) => <article className="integration-card" key={model.id}><div><strong>{model.alias}</strong><small>Private gateway model alias</small></div><button className="danger-button" disabled={busy} onClick={() => void removeLiteLlmModel(model)} type="button">Remove model</button></article>)}</div> : null}
      </section> : null}
      <section className="setup-card" aria-labelledby="experimental-scraper-heading">
        <p className="section-kicker">Experimental provider</p>
        <h3 id="experimental-scraper-heading">ForexFactory scraper</h3>
        <p>Local development inspection only. Imported data is marked <code>SCRAPED_EXPERIMENTAL</code>; it is not a healthy provider connection, official calendar coverage, market evidence, or recommendation-gate input.</p>
        <form className="setup-form" onSubmit={importExperimentalCalendar}>
          <div className="form-row">
            <label>Start date<input name="scraper-start-date" required type="date" /></label>
            <label>End date<input name="scraper-end-date" required type="date" /></label>
          </div>
          <label>Sources (optional, comma-separated)<input name="scraper-sources" placeholder="forex, cryptocraft, energyexch, metalsmine" /></label>
          <div className="form-row">
            <label>Limit<input defaultValue="100" max="500" min="1" name="scraper-limit" required type="number" /></label>
            <label>Offset<input defaultValue="0" min="0" name="scraper-offset" required type="number" /></label>
          </div>
          <p className="field-hint">Leave sources blank for ForexFactory. The date range is limited to 31 days; each source/date uses the scraper's daily endpoint.</p>
          <button className="secondary-button" disabled={busy} type="submit">Run experimental scraper import</button>
        </form>
        {experimentalImportStatus ? <p className="field-hint" role="status">{experimentalImportStatus}</p> : null}
        <div className="integration-form-actions"><h4>Cached import results</h4><button className="secondary-button" disabled={busy} onClick={() => void refreshExperimentalCache()} type="button">Refresh cached results</button></div>
        {experimentalCacheState === "LOADING" ? <p className="field-hint">Loading the persisted experimental cache…</p> : null}
        {experimentalCacheState === "IMPORT_QUEUED" ? <p className="field-hint">Import queued. TraderX will refresh this cache automatically; use Refresh cached results if it takes longer.</p> : null}
        {experimentalCacheState === "EMPTY" ? <p className="empty-state">No cached experimental events yet. Start the experimental Docker profile, submit an import, then refresh this result list.</p> : null}
        {experimentalCacheState === "UNAVAILABLE" ? <p className="status-message" data-tone="error">TraderX could not read the experimental cache. Confirm that the API is running and that you are signed in.</p> : null}
        {experimentalCacheState === "READY" ? <div className="evidence-metrics">{experimentalEvents.slice(0, 6).map((event) => <div key={event.id}><strong>{event.importance} · {event.event_type}</strong><span>{event.title} · {new Date(event.scheduled_at).toLocaleString()} · SCRAPED_EXPERIMENTAL</span><a href={event.official_url} rel="noreferrer" target="_blank">Scraped source</a></div>)}</div> : null}
      </section>
      {healthyProviders.length > 0 ? <><h3>Healthy connections</h3><div className="active-market-grid">{healthyProviders.map((item) => <article key={item.provider}><span>{item.category === "LLM" ? "Advisory model" : item.asset_categories.join(", ") || "Market data"}</span><strong>{providerNames[item.provider]}</strong><small>Connected and healthy · {item.retention_posture}</small>{item.category === "LLM" ? <small>Models: choose any compatible model ID in Markets</small> : item.permitted_models.length ? <small>Models: {item.permitted_models.join(", ")}</small> : null}</article>)}</div></> : <p className="empty-state">No healthy research-provider connections yet. Select a reviewed provider below to configure and test it.</p>}
      {definition ? <form aria-label="Connect reviewed research provider" className="integration-form" onSubmit={connect}><label htmlFor="provider-kind">Research provider<select id="provider-kind" onChange={(event) => setSelected(event.target.value)} value={selected}>{catalogue.map((item) => <option key={item.provider} value={item.provider}>{providerNames[item.provider]}</option>)}</select></label><label htmlFor="provider-name">Connection name<input defaultValue={`${providerNames[definition.provider]} research`} id="provider-name" name="provider-name" required /></label>{definition.provider === "LITELLM_PROXY" ? <p className="field-hint">LiteLLM keeps the underlying provider credentials, routing, and configured model aliases in one gateway. For the bundled service use <code>http://litellm:4000/v1</code>; for a remote gateway use its HTTPS API base URL.</p> : null}{definition.configuration_fields.map((field) => <label key={field}>{field.replaceAll("_", " ")}<input defaultValue={definition.provider === "LITELLM_PROXY" && field === "base_url" ? "http://litellm:4000/v1" : undefined} name={`configuration-${field}`} required /></label>)}{definition.credential_fields.map((field) => <label key={field}>{field.replaceAll("_", " ")}<input autoComplete="new-password" name={`credential-${field}`} required type="password" /></label>)}<label className="confirmation-check"><input name="licensing-accepted" required={Boolean(definition.licensing_notice)} type="checkbox" /> I accept the licensing/data-use prerequisites.</label><label className="confirmation-check"><input name="retention-accepted" required={definition.retention_posture !== "NOT_APPLICABLE"} type="checkbox" /> I reviewed the provider retention posture.</label><label htmlFor="provider-reason">Reason<textarea id="provider-reason" minLength={8} name="provider-reason" required /></label><button disabled={busy} type="submit">Connect reviewed provider</button></form> : null}
      <div className="integration-list">{configured.map((integration) => {
        const provider = catalogue.find((item) => item.provider === integration.provider);
        return <article className="integration-card" key={integration.id}>
          <div><p className="section-kicker">{integration.category}</p><h3>{integration.name}</h3><p>{providerNames[integration.provider] ?? integration.provider} · {integration.state} · entitlement {integration.entitlement_status}</p><small>Catalogue {integration.catalogue_revision} · credential {integration.credential_status} · {integration.credential}</small></div>
          <div className="integration-actions"><button disabled={busy} onClick={() => void testProvider(integration)} type="button">Test provider</button><button className="secondary-button" disabled={busy} onClick={() => void lifecycle(integration, integration.state === "DISABLED" ? "ENABLE" : "DISABLE")} type="button">{integration.state === "DISABLED" ? "Enable provider" : "Disable provider"}</button><button className="danger-button" disabled={busy} onClick={() => void removeProvider(integration)} type="button">Remove provider</button></div>
          {provider?.credential_fields.length ? <details><summary>Rotate write-only credential</summary><form className="integration-form" onSubmit={(event) => void rotateCredential(event, integration)}>{provider.credential_fields.map((field) => <label key={field}>New {field.replaceAll("_", " ")}<input autoComplete="new-password" name={`rotate-${field}`} required type="password" /></label>)}<button disabled={busy} type="submit">Rotate credential</button></form></details> : null}
          {provider?.entitlement_required && integration.entitlement_status !== "VERIFIED" ? <details><summary>Record paid entitlement evidence</summary><form className="integration-form" onSubmit={(event) => void declareEntitlement(event, integration)}><p>The reference is hashed in the audit ledger. TraderX marks the entitlement verified only after the reviewed provider endpoint accepts the live test.</p><label>Entitlement evidence reference<input name="entitlement-reference" required /></label><label>Reason<textarea minLength={8} name="entitlement-reason" required /></label><button disabled={busy} type="submit">Submit entitlement for verification</button></form></details> : null}
        </article>;
      })}</div>
      {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
      {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
    </section>
  );
}
