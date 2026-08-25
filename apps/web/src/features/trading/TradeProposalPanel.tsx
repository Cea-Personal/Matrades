"use client";

import { RiskSnapshot, type Snapshot } from "@/features/risk/RiskSnapshot";

export type Proposal = { id: string; instrument: string; direction: string; entry: string; stop_loss: string; targets: string[]; approved_size: string; invalidation: string; critic_result: string; instrument_type?: string; venue_instrument_id?: string; specification_version_id?: string; futures_contract_id?: string; risk: { decision: "PASS" | "REDUCE_SIZE" | "HARD_BLOCK"; reasons: string[]; limiting_constraints: string[]; snapshot: Snapshot } };

export function TradeProposalPanel({ proposal, onDecision }: { proposal: Proposal; onDecision?: (action: "TAKE" | "WAIT" | "REJECT") => void }) {
  const tone = proposal.risk.decision === "PASS" ? "good" : proposal.risk.decision === "REDUCE_SIZE" ? "warn" : "bad";
  return <article><header className="card"><p className="muted">HIL-2 proposal</p><h1>{proposal.instrument} {proposal.direction}</h1><strong className={tone}>{proposal.risk.decision.replace("_", " ")}</strong><p>Entry {proposal.entry} · Stop {proposal.stop_loss} · Size {proposal.approved_size}</p>{proposal.instrument_type && <p>Exact {proposal.instrument_type} listing {proposal.venue_instrument_id ?? "missing"} · specification {proposal.specification_version_id ?? "missing"}{proposal.futures_contract_id ? ` · contract ${proposal.futures_contract_id}` : ""}</p>}<p className="muted">{proposal.risk.reasons.join(" ")}</p><p>Critic: {proposal.critic_result}</p></header><RiskSnapshot snapshot={proposal.risk.snapshot}/>{proposal.risk.decision !== "HARD_BLOCK" && <div className="actions" aria-label="Human decision"><button className="btn primary" onClick={() => onDecision?.("TAKE")}>Take manually</button><button className="btn" onClick={() => onDecision?.("WAIT")}>Wait</button><button className="btn" onClick={() => onDecision?.("REJECT")}>Reject</button></div>}</article>;
}
