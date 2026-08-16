"use client";

import { useCallback, useEffect, useState } from "react";

type Health = {
  status: string;
  components: Record<string, string>;
  safety_impact: string[];
  circuit_breakers: Array<{ id: string; type: string; state: string; reason?: string }>;
  integration_observations: Array<{
    id: string;
    integration_id: string;
    status: string;
    evidence: Record<string, unknown>;
    observed_at: string;
    affected_capabilities?: string[];
    current_error?: string | null;
  }>;
  strategy_health: Array<{
    id: string;
    strategy_version_id: string;
    state: string;
    evidence: Record<string, unknown>;
    observed_at: string;
  }>;
  secrets_redacted: boolean;
};

type Audit = {
  id: string;
  action: string;
  outcome: string;
  actor_role?: string;
  target_type: string;
  reason?: string;
  occurred_at: string;
  correlation_id: string;
};

export function SystemControl() {
  const [health, setHealth] = useState<Health>();
  const [audit, setAudit] = useState<Audit[]>([]);
  const [action, setAction] = useState("");
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [healthResponse, auditResponse] = await Promise.all([
        fetch("/api/v1/operations/health", { credentials: "same-origin" }),
        fetch(`/api/v1/operations/audit${action ? `?action=${encodeURIComponent(action)}` : ""}`, {
          credentials: "same-origin"
        })
      ]);
      if (!healthResponse.ok || !auditResponse.ok) throw new Error("unavailable");
      setHealth(await healthResponse.json() as Health);
      setAudit((await auditResponse.json() as { items: Audit[] }).items);
      setError(undefined);
    } catch {
      setError("TraderX could not load redacted operational evidence.");
    }
  }, [action]);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const integrationObservations = health?.integration_observations ?? [];
  const strategyHealth = health?.strategy_health ?? [];

  return <section aria-labelledby="system-control">
    <h3 id="system-control">System health and append-only audit</h3>
    <p>Health impact is explicit and secrets remain redacted from every response.</p>
    {health ? <>
      <p className="status-message" data-tone={health.status === "HEALTHY" ? "success" : "error"}>
        <strong>Overall {health.status}</strong>
        {health.safety_impact.length ? ` · affected: ${health.safety_impact.join(", ")}` : " · all observed components healthy"}
      </p>
      <dl className="evidence-metrics">
        {Object.entries(health.components).map(([name, state]) => <div key={name}><dt>{name}</dt><dd>{state}</dd></div>)}
      </dl>
      <section aria-labelledby="integration-observations">
        <h4 id="integration-observations">Integration and data freshness</h4>
        {integrationObservations.length ? <ol className="timeline">
          {integrationObservations.map((observation) => <li key={observation.id}>
            <strong>{observation.status} · {String(observation.evidence.provider ?? "integration")}</strong>
            <span>{String(observation.evidence.category ?? "provider")} · {String(observation.evidence.integration_state ?? "UNKNOWN")} · entitlement {String(observation.evidence.entitlement_status ?? "not required")} · credential redacted</span>
            {observation.affected_capabilities?.length ? <span>Affected: {observation.affected_capabilities.join(", ")}</span> : null}
            {observation.current_error ? <span>Action required: {observation.current_error.replaceAll("_", " ")}</span> : null}
            <small>{new Date(observation.observed_at).toLocaleString()}</small>
          </li>)}
        </ol> : <p className="workspace-notice">No integration health observation has been recorded yet.</p>}
      </section>
      <section aria-labelledby="strategy-health">
        <h4 id="strategy-health">Live strategy health</h4>
        {strategyHealth.length ? <ol className="timeline">
          {strategyHealth.map((observation) => <li key={observation.id}>
            <strong>{observation.state} · version {observation.strategy_version_id.slice(0, 8)}</strong>
            <span>{String(observation.evidence.sample_size ?? 0)} live journal samples · current average R {String(observation.evidence.current_average_r ?? "unavailable")}</span>
            <small>{new Date(observation.observed_at).toLocaleString()}</small>
          </li>)}
        </ol> : <p className="workspace-notice">No live-approved strategy has enough observed evidence yet.</p>}
      </section>
      {health.circuit_breakers.length ? <section aria-labelledby="circuit-breakers">
        <h4 id="circuit-breakers">Active circuit breakers</h4>
        <ul>{health.circuit_breakers.map((breaker) => <li key={breaker.id}>{breaker.type} · {breaker.state} · {breaker.reason}</li>)}</ul>
      </section> : null}
    </> : null}
    <label>Audit action filter<input onChange={(event) => setAction(event.target.value)} placeholder="e.g. strategy.approval.decide" value={action} /></label>
    {audit.length ? <div className="evidence-table">
      {audit.map((item) => <div className="evidence-row" key={item.id}><span><strong>{item.action}</strong><small>{new Date(item.occurred_at).toLocaleString()}</small></span><span>{item.outcome}</span><span>{item.target_type}</span><span>{item.actor_role ?? "SYSTEM"}</span></div>)}
    </div> : <p className="workspace-notice">No audit event matches this filter.</p>}
    {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
  </section>;
}
