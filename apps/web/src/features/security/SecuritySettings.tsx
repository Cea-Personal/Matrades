"use client";

import { useAuth } from "@/lib/providers";

export function SecuritySettings() {
  const { user } = useAuth();
  const emailStatus = user?.email_verified
    ? "Verified"
    : user?.email_verification_required
      ? "Not verified"
      : "Paused temporarily";

  return (
    <section className="section-stack" id="security-settings">
      <header><p className="eyebrow">Identity</p><h2>Security</h2></header>
      <article className="card">
        <h2>Account activation</h2>
        <dl className="metric-list">
          <div><dt>Email</dt><dd>{user?.email}</dd></div>
          <div>
            <dt>Email verification</dt>
            <dd className={user?.email_verified ? "good" : user?.email_verification_required ? "bad" : "muted"}>
              {emailStatus}
            </dd>
          </div>
          <div><dt>MFA enrolled</dt><dd className={user?.mfa_enabled ? "good" : "bad"}>{user?.mfa_enabled ? "Yes" : "No"}</dd></div>
          <div><dt>Role</dt><dd>{user?.role}</dd></div>
        </dl>
        <p className="muted">Sensitive removals request MFA in the confirmation dialog at the point of removal.</p>
      </article>
    </section>
  );
}
