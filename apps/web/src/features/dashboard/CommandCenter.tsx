"use client";

import { AccountRiskSetup, type AccountSummary } from "@/features/risk/AccountRiskSetup";
import { CommandCenterWorkspace } from "./CommandCenterWorkspace";

export type Dashboard = {
  account: AccountSummary | null;
  risk: {
    state: string;
    capacity: number;
    quality: string;
    reason_codes: string[];
    remaining_daily_margin?: string;
    remaining_drawdown_margin?: string;
    open_risk?: string;
  };
  metrics: {
    balance: string;
    equity: string;
    realized_pl: string;
    floating_pl: string;
    observed_at: string;
  } | null;
  onboarding: {
    account_configured: boolean;
    prop_profile_configured: boolean;
    risk_policy_configured: boolean;
    account_data_verified: boolean;
  };
  active_markets: Array<{ category: string; symbol: string }>;
  opportunities: Array<{ id: string; state: string; score: string | null }>;
  critical_alerts: Array<{ kind: string; title: string; state: string; reason: string | null }>;
  integration_health: Array<{ id: string; name: string; status: string; observed_at: string | null }>;
  research_connection_progress?: Array<{
    provider: string;
    label: string;
    required: boolean;
    complete: boolean;
  }>;
  workspace_prerequisites?: Array<{ label: string; target: WorkspaceTarget; required: boolean; complete: boolean; purpose: string }>;
  workflow_progress?: {
    healthy_integrations: number;
    published_market_research_runs: number;
    successful_strategy_versions: number;
    active_paper_runs: number;
  };
};

function valueOrPending(value: string | undefined): string {
  return value ?? "Awaiting verified data";
}

type WorkspaceTarget = "account-risk" | "integrations" | "markets" | "strategies" | "paper" | "opportunities" | "monitoring";

export function CommandCenter({ dashboard, onAccountChanged }: { dashboard: Dashboard; onAccountChanged: () => Promise<void> }) {
  const {
    account,
    metrics,
    onboarding,
    risk,
    active_markets = [],
    opportunities = [],
    critical_alerts = [],
    integration_health = [],
    research_connection_progress = [],
    workspace_prerequisites = [],
    workflow_progress = {
      healthy_integrations: 0,
      published_market_research_runs: 0,
      successful_strategy_versions: 0,
      active_paper_runs: 0
    }
  } = dashboard;
  const stateClass = risk.state.toLowerCase();
  const steps: Array<[string, boolean]> = [
    ["Account identity", onboarding.account_configured],
    ["External loss rules", onboarding.prop_profile_configured],
    ["Internal guardrails", onboarding.risk_policy_configured],
    ["Verified account data", onboarding.account_data_verified]
  ];
  const activationSteps: Array<{ label: string; complete: boolean; detail: string; target: WorkspaceTarget }> = [
    { label: "Initial setup", complete: true, detail: "Done", target: "account-risk" },
    ...steps.map(([label, complete]) => ({
      label,
      complete,
      detail: complete ? "Done" : "Required",
      target: label === "Verified account data" ? "integrations" as const : "account-risk" as const
    })),
    ...research_connection_progress.map((connection) => ({
      label: `${connection.label} connection`,
      complete: connection.complete,
      detail: `${connection.required ? "Required" : "Optional"} · ${connection.complete ? "done" : "not connected"}`,
      target: "integrations" as const
    })),
    ...workspace_prerequisites.map((step) => ({ label: step.label, complete: step.complete, detail: `${step.required ? "Required" : "Optional"} for ${step.purpose} · ${step.complete ? "done" : "not ready"}`, target: step.target }))
  ];
  const readyForWorkspace = onboarding.account_configured
    && onboarding.prop_profile_configured
    && onboarding.risk_policy_configured;

  function openWorkspace(target: WorkspaceTarget) {
    window.dispatchEvent(new CustomEvent("traderx:workspace", { detail: target }));
    window.history.replaceState(null, "", `/command-center?workspace=${target}`);
    window.requestAnimationFrame(() => {
      const destination = document.getElementById("traderx-workspace") ?? document.getElementById("account-risk-setup");
      destination?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (destination instanceof HTMLElement) destination.focus({ preventScroll: true });
    });
  }

  return (
    <section className="command-center" aria-label="Command Center">
      <header className="command-hero">
        <div><p className="eyebrow">Authenticated control plane</p><h1>Command Center</h1><p>Decision support only. TraderX cannot submit, modify, or close an order.</p></div>
        <div className={`risk-state risk-state-${stateClass}`}><span>Risk state</span><strong>{risk.state}</strong><small>{risk.capacity} of 2 position slots available</small></div>
      </header>

      <div className="command-layout">
        <aside className="activation-sidebar" aria-labelledby="activation-sidebar-heading">
          <p className="section-kicker">Activation progress</p>
          <h2 id="activation-sidebar-heading">Safe activation checklist</h2>
          <ol>{activationSteps.map((step) => <li className={step.complete ? "complete" : "pending"} key={step.label}><span aria-hidden="true">{step.complete ? "✓" : "○"}</span><button aria-label={`Open ${step.label} workspace`} onClick={() => openWorkspace(step.target)} type="button"><strong>{step.label}</strong><small>{step.detail}</small></button></li>)}</ol>
        </aside>

        <div className="command-main">
          <section className="risk-gate" aria-labelledby="risk-gate-heading">
            <div><p className="section-kicker">Recommendation gate</p><h2 id="risk-gate-heading">{risk.state === "LOCKDOWN" ? "New recommendations are blocked" : "Risk controls are active"}</h2><p>{risk.reason_codes.map((code) => code.replaceAll("_", " ").toLowerCase()).join(" · ") || "No blocking reason is recorded."}</p></div>
            <p className="gate-detail">TraderX fails closed whenever account, position, price, or risk evidence is incomplete.</p>
          </section>

          <section className="metric-grid" aria-label="Account risk summary">
            <article><span>Account</span><strong>{account?.name ?? "Not registered"}</strong><small>{account ? `${account.mode} · ${account.currency}` : "Register one primary account to begin."}</small></article>
            <article><span>Equity</span><strong>{valueOrPending(metrics?.equity)}</strong><small>{metrics ? `Balance ${metrics.balance}` : "No verified account snapshot"}</small></article>
            <article><span>Loss margins</span><strong>{valueOrPending(risk.remaining_daily_margin)}</strong><small>Daily margin · overall {valueOrPending(risk.remaining_drawdown_margin)}</small></article>
            <article><span>Open risk</span><strong>{valueOrPending(risk.open_risk)}</strong><small>Data quality: {risk.quality}</small></article>
          </section>

          <section className="activity-summary" aria-label="Current TraderX evidence">
            <article><span>Active markets</span><strong>{active_markets.length} / 3</strong><small>{active_markets.length ? active_markets.map((market) => market.symbol).join(" · ") : "No market has been approved"}</small></article>
            <article><span>Opportunities</span><strong>{opportunities.length}</strong><small>{opportunities.length ? `${opportunities.filter((opportunity) => opportunity.state === "CANDIDATE").length} candidates awaiting risk review` : "No current opportunity evidence"}</small></article>
            <article><span>Critical alerts</span><strong>{critical_alerts.length}</strong><small>{critical_alerts.length ? critical_alerts[0].title : "No critical alert recorded"}</small></article>
            <article><span>Integration health</span><strong>{integration_health.length}</strong><small>{integration_health.length ? integration_health.map((integration) => `${integration.name}: ${integration.status}`).join(" · ") : "No account connection recorded"}</small></article>
          </section>

          {!readyForWorkspace ? (
            <AccountRiskSetup account={account} onAccountChanged={onAccountChanged} />
          ) : (
            <CommandCenterWorkspace account={account} onAccountChanged={onAccountChanged} startAtMarkets={onboarding.account_data_verified} />
          )}
        </div>
      </div>
    </section>
  );
}
