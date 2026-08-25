"use client";

import { FormEvent, useState } from "react";

type MfaDeleteDialogProps = {
  targetLabel: string;
  scope: string;
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: (code: string) => void;
};

export function MfaDeleteDialog({
  targetLabel,
  scope,
  busy,
  error,
  onCancel,
  onConfirm,
}: MfaDeleteDialogProps) {
  const [code, setCode] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code) onConfirm(code);
  };

  return <div className="modal-backdrop" role="presentation">
    <form className="card modal" role="dialog" aria-modal="true" aria-labelledby="mfa-delete-title" onSubmit={submit}>
      <h2 id="mfa-delete-title">Confirm removal</h2>
      <p className="muted">Remove <strong>{targetLabel}</strong>? This action requires the <code>{scope}</code> MFA step-up.</p>
      <label>Authenticator or recovery code<input required autoFocus type="password" value={code} onChange={event => setCode(event.target.value)} /></label>
      {error ? <p className="notice bad">{error}</p> : null}
      <div className="actions"><button className="btn primary" disabled={busy || !code}>{busy ? "Verifying…" : "Verify and remove"}</button><button type="button" className="btn" disabled={busy} onClick={onCancel}>Cancel</button></div>
    </form>
  </div>;
}
