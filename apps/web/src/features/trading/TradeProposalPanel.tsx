"use client";

import { RiskSnapshot } from "@/features/risk/RiskSnapshot";

type Plan = {
  id: string;
  instrument: string;
  state: string;
  construction?: { direction?: string; entry?: string; stop_loss?: string; approved_size?: string };
  risk: { decision: string; reasons: string[]; snapshot: Parameters<typeof RiskSnapshot>[0]["snapshot"] };
};

/** Compatibility filename retained for imports; the panel is now read-only Trade Plan evidence. */
export function TradeProposalPanel({ plan }: { plan: Plan }) {
  return <article><header className="card"><p className="muted">Autonomous Trade Plan</p><h1>{plan.instrument} {plan.construction?.direction ?? ""}</h1><strong>{plan.state} · {plan.risk.decision.replace("_", " ")}</strong><p>Entry {plan.construction?.entry ?? "—"} · Stop {plan.construction?.stop_loss ?? "—"} · Size {plan.construction?.approved_size ?? "—"}</p><p className="muted">{plan.risk.reasons.join(" ")}</p></header><RiskSnapshot snapshot={plan.risk.snapshot} /></article>;
}
