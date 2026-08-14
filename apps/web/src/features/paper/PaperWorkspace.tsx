"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApprovalReview } from "./ApprovalReview";
import { PaperTrading, type PaperRunEvidence } from "./PaperTrading";

type Version = { id: string; sequence: number; lifecycle: string; etag: string };
type Strategy = { id: string; name: string; versions: Version[] };
type Validation = { id: string; strategy_version_id: string; manifest_hash: string; state: string };

export function PaperWorkspace() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [validations, setValidations] = useState<Validation[]>([]);
  const [runs, setRuns] = useState<PaperRunEvidence[]>([]);
  const [versionId, setVersionId] = useState("");
  const [validationId, setValidationId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const responses = await Promise.all([
        fetch("/api/v1/strategies", { credentials: "same-origin" }),
        fetch("/api/v1/validation/runs", { credentials: "same-origin" }),
        fetch("/api/v1/paper/runs", { credentials: "same-origin" })
      ]);
      if (responses.some((response) => !response.ok)) throw new Error("unavailable");
      const strategyItems = (await responses[0].json() as { items: Strategy[] }).items;
      const validationItems = (await responses[1].json() as { items: Validation[] }).items;
      const runItems = (await responses[2].json() as { items: PaperRunEvidence[] }).items;
      setStrategies(strategyItems);
      setValidations(validationItems);
      setRuns(runItems);
      if (!versionId) {
        const ready = strategyItems.flatMap((strategy) => strategy.versions).find((version) => version.lifecycle === "BACKTEST_PASSED" || version.lifecycle === "PAPER_TRADING" || version.lifecycle === "AWAITING_APPROVAL");
        if (ready) setVersionId(ready.id);
      }
      if (!selectedRunId && runItems[0]) setSelectedRunId(runItems[0].id);
      setError(undefined);
    } catch {
      setError("TraderX could not load paper-trading evidence.");
    }
  }, [selectedRunId, versionId]);

  useEffect(() => {
    void Promise.resolve().then(load);
    // Initial external data load only; actions refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const eligibleValidations = useMemo(() => validations.filter((item) => item.strategy_version_id === versionId && item.state === "PASS"), [validations, versionId]);
  const selectedRun = runs.find((run) => run.id === selectedRunId);
  const selectedVersion = strategies.flatMap((strategy) => strategy.versions).find((version) => version.id === selectedRun?.strategy_version_id);

  async function startRun() {
    const validation = eligibleValidations.find((item) => item.id === validationId) ?? eligibleValidations[0];
    if (!versionId || !validation) return;
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      const response = await fetch("/api/v1/paper/runs", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ strategy_version_id: versionId, validation_run_id: validation.id, evidence_manifest_hash: validation.manifest_hash })
      });
      const payload = await response.json() as { run?: PaperRunEvidence; detail?: string };
      if (!response.ok || !payload.run) { setError(payload.detail ?? "Paper evaluation could not start."); return; }
      setSelectedRunId(payload.run.id);
      setMessage(payload.run.state === "AWAITING_APPROVAL" ? "Paper evidence passed and now awaits a human decision." : "Paper evaluation completed. Review the unmet evidence before approval.");
      await load();
    } catch { setError("TraderX could not complete the paper evaluation."); }
    finally { setBusy(false); }
  }

  async function decide(decision: "APPROVE_LIVE" | "REJECT" | "RETURN_TO_RESEARCH", reason: string, mfaCode: string) {
    if (!selectedRun || !selectedVersion) return;
    setBusy(true); setError(undefined); setMessage(undefined);
    try {
      if (decision === "APPROVE_LIVE") {
        const stepUp = await fetch("/api/v1/auth/mfa/verify", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: mfaCode }) });
        if (!stepUp.ok) { const problem = await stepUp.json() as { detail?: string }; setError(problem.detail ?? "Recent MFA verification failed."); return; }
      }
      const response = await fetch(`/api/v1/approvals/strategies/${selectedRun.strategy_version_id}`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "If-Match": selectedVersion.etag, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ paper_run_id: selectedRun.id, decision, reason, confirmation: "CONFIRMED" })
      });
      const payload = await response.json() as { detail?: string };
      if (!response.ok) { setError(payload.detail ?? "The approval decision was not recorded."); return; }
      setMessage(`Decision recorded: ${decision.replaceAll("_", " ")}.`);
      await load();
    } catch { setError("TraderX could not record the approval decision."); }
    finally { setBusy(false); }
  }

  return <div className="governed-workspace">
    <PaperTrading busy={busy} eligibleValidations={eligibleValidations} onRun={startRun} onSelectRun={setSelectedRunId} onSelectValidation={setValidationId} onSelectVersion={setVersionId} runs={runs} selectedRunId={selectedRunId} selectedValidationId={validationId} selectedVersionId={versionId} strategies={strategies} />
    <ApprovalReview busy={busy} onDecide={decide} run={selectedRun} />
    {message ? <p className="status-message" data-tone="success" role="status">{message}</p> : null}
    {error ? <p className="status-message" data-tone="error" role="alert">{error}</p> : null}
  </div>;
}
