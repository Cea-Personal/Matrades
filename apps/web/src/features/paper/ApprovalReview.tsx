"use client";

import { useState } from "react";

import type { PaperRunEvidence } from "./PaperTrading";

export function ApprovalReview({ run, busy, onDecide }: { run?: PaperRunEvidence; busy: boolean; onDecide: (decision: "APPROVE_LIVE" | "REJECT" | "RETURN_TO_RESEARCH", reason: string, mfaCode: string) => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const eligible = run?.state === "AWAITING_APPROVAL" && run.criteria.eligible;
  return <section aria-labelledby="approval-review"><h3 id="approval-review">Deliberate strategy approval</h3><p>Paper evidence never promotes itself. An authorized owner must review current evidence, confirm the decision, and provide a fresh MFA code.</p>{run ? <div className="setup-form"><label>Decision reason<textarea onChange={(event) => setReason(event.target.value)} placeholder="Explain why this evidence supports the decision." value={reason} /></label><label>MFA code for live approval<input autoComplete="one-time-code" inputMode="numeric" maxLength={6} onChange={(event) => setMfaCode(event.target.value)} value={mfaCode} /></label><label className="confirmation-check"><input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" /> I understand this grants decision-support eligibility only; TraderX still cannot place an order.</label><div className="button-row"><button disabled={!eligible || !confirmed || reason.length < 8 || mfaCode.length !== 6 || busy} onClick={() => onDecide("APPROVE_LIVE", reason, mfaCode)} type="button">Approve for live decision support</button><button className="secondary-button" disabled={!confirmed || reason.length < 8 || busy} onClick={() => onDecide("RETURN_TO_RESEARCH", reason, "")} type="button">Return to research</button><button className="danger-button" disabled={!confirmed || reason.length < 8 || busy} onClick={() => onDecide("REJECT", reason, "")} type="button">Reject</button></div>{!eligible ? <p className="workspace-notice">Live approval remains unavailable until the combined paper evidence reaches AWAITING APPROVAL.</p> : null}</div> : <p className="workspace-notice">Select or run a paper evaluation before making a decision.</p>}</section>;
}
