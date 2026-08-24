export type Snapshot = { account_equity: string; starting_account: string; current_drawdown: string; maximum_allowed_drawdown: string; remaining_drawdown: string; daily_loss_remaining: string; existing_open_risk: string; candidate_trade_risk: string; portfolio_risk_after_trade: string; open_trades: number; max_concurrent_trades: number; additional_trade_capacity: number };

export function RiskSnapshot({ snapshot }: { snapshot: Snapshot }) {
  const cards = [["Account equity", snapshot.account_equity], ["Current drawdown", snapshot.current_drawdown], ["Remaining drawdown", snapshot.remaining_drawdown], ["Daily loss remaining", snapshot.daily_loss_remaining], ["Reserved open risk", snapshot.existing_open_risk], ["Candidate risk", snapshot.candidate_trade_risk], ["Portfolio after trade", snapshot.portfolio_risk_after_trade], ["Additional capacity", String(snapshot.additional_trade_capacity)]];
  return <section><h2>Pre-trade equity snapshot</h2><div className="grid">{cards.map(([label, value]) => <article className="card" key={label}><div className="muted">{label}</div><strong>{value}</strong></article>)}</div></section>;
}
