import { AccountRiskSetup, type AccountSummary } from "@/features/risk/AccountRiskSetup";

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
};

function valueOrPending(value: string | undefined): string {
  return value ?? "Awaiting verified data";
}

export function CommandCenter({ dashboard, onAccountChanged }: { dashboard: Dashboard; onAccountChanged: () => Promise<void> }) {
  const { account, metrics, onboarding, risk } = dashboard;
  const stateClass = risk.state.toLowerCase();
  const steps: Array<[string, boolean]> = [
    ["Account identity", onboarding.account_configured],
    ["External loss rules", onboarding.prop_profile_configured],
    ["Internal guardrails", onboarding.risk_policy_configured],
    ["Verified account data", onboarding.account_data_verified]
  ];

  return (
    <section className="command-center" aria-label="Command Center">
      <header className="command-hero">
        <div><p className="eyebrow">Authenticated control plane</p><h1>Command Center</h1><p>Decision support only. TraderX cannot submit, modify, or close an order.</p></div>
        <div className={`risk-state risk-state-${stateClass}`}><span>Risk state</span><strong>{risk.state}</strong><small>{risk.capacity} of 2 position slots available</small></div>
      </header>

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

      <section className="readiness-card" aria-labelledby="readiness-heading">
        <div><p className="section-kicker">Safe activation checklist</p><h2 id="readiness-heading">What TraderX still needs</h2></div>
        <ol>{steps.map(([label, complete]) => <li className={complete ? "complete" : "pending"} key={label}><span aria-hidden="true">{complete ? "✓" : "○"}</span>{label}<small>{complete ? "Recorded" : "Required"}</small></li>)}</ol>
      </section>

      <AccountRiskSetup account={account} onAccountChanged={onAccountChanged} />
    </section>
  );
}
