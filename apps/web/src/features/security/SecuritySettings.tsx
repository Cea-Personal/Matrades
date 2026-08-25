"use client";

import { useAuth } from "@/lib/providers";

export function SecuritySettings() {
  const { user } = useAuth();
  return <section className="section-stack" id="security-settings"><header><p className="eyebrow">Identity</p><h1>Security</h1></header><article className="card"><h2>Account activation</h2><dl className="metric-list"><div><dt>Email</dt><dd>{user?.email}</dd></div><div><dt>Email verified</dt><dd className={user?.email_verified?"good":"bad"}>{user?.email_verified?"Yes":"No"}</dd></div><div><dt>MFA enrolled</dt><dd className={user?.mfa_enabled?"good":"bad"}>{user?.mfa_enabled?"Yes":"No"}</dd></div><div><dt>Role</dt><dd>{user?.role}</dd></div></dl><p className="muted">Sensitive removals request MFA in the confirmation dialog at the point of removal.</p></article></section>;
}
