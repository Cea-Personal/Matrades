"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type AuthRoute = "setup" | "sign-in" | "mfa-enroll" | "mfa-verify" | "mfa-recovery" | "password-reset";
type LoginStatus = "AUTHENTICATED" | "MFA_ENROLLMENT_REQUIRED" | "MFA_REQUIRED";

type LoginResult = {
  status: LoginStatus;
  recovery_codes?: string[];
};

type EnrollmentResult = { provisioning_uri: string };
type BootstrapStatus = { bootstrap_available: boolean };
type ApiProblem = { detail?: string; title?: string };

function errorMessage(problem: ApiProblem): string {
  return problem.detail ?? problem.title ?? "The request could not be completed. Please try again.";
}

async function request<T>(path: string, body?: object): Promise<{ response: Response; result: T & ApiProblem }> {
  const response = await fetch(`/api/v1${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined
  });
  const result = (await response.json().catch(() => ({}))) as T & ApiProblem;
  return { response, result };
}

function StatusMessage({ message, tone = "info" }: { message?: string; tone?: "error" | "info" | "success" }) {
  return message ? <p className="status-message" data-tone={tone} role={tone === "error" ? "alert" : "status"}>{message}</p> : null;
}

function AuthFrame({ children, route }: { children: React.ReactNode; route: AuthRoute }) {
  const copy: Record<AuthRoute, { eyebrow: string; title: string; detail: string }> = {
    setup: {
      eyebrow: "First-time setup",
      title: "Start with a protected control plane.",
      detail: "Create the single owner account for this TraderX installation. You will secure it with your authenticator next."
    },
    "sign-in": {
      eyebrow: "Welcome back",
      title: "Your decisions deserve a clear risk boundary.",
      detail: "Sign in to review the evidence, risk state, and decision-support tools available to you."
    },
    "mfa-enroll": {
      eyebrow: "Account security",
      title: "Keep account control in your hands.",
      detail: "An authenticator is required before TraderX exposes account or operational information."
    },
    "mfa-verify": {
      eyebrow: "Account security",
      title: "Confirm it is you.",
      detail: "Enter the current code from your authenticator to continue securely."
    },
    "mfa-recovery": {
      eyebrow: "Account recovery",
      title: "Recover without weakening security.",
      detail: "A one-time recovery code starts a fresh authenticator enrollment and revokes old sessions."
    },
    "password-reset": {
      eyebrow: "Account recovery",
      title: "Reset your password, keep your second factor.",
      detail: "A reset link alone is not enough to restore an operational session. TraderX will still verify your second factor."
    }
  };
  const content = copy[route];

  return (
    <div className="auth-layout">
      <aside className="auth-aside" aria-label="TraderX security principles">
        <p className="eyebrow">{content.eyebrow}</p>
        <h2>{content.title}</h2>
        <p>{content.detail}</p>
        <ul>
          <li>Manual execution only</li>
          <li>Risk controls fail closed</li>
          <li>Every material action is auditable</li>
        </ul>
      </aside>
      {children}
    </div>
  );
}

export function AuthEntryLinks() {
  const [bootstrapAvailable, setBootstrapAvailable] = useState(true);

  useEffect(() => {
    void request<BootstrapStatus>("/auth/bootstrap-status")
      .then(({ response, result }) => {
        if (response.ok) setBootstrapAvailable(result.bootstrap_available);
      })
      .catch(() => undefined);
  }, []);

  return (
    <nav className="auth-entry-links" aria-label="Authentication">
      <Link href="/sign-in">Sign in</Link>
      {bootstrapAvailable ? <Link href="/setup">Set up the initial owner</Link> : null}
    </nav>
  );
}

export function AuthScreen({ route, notice }: { route: AuthRoute; notice?: string }) {
  const router = useRouter();
  const [ready, setReady] = useState(route !== "setup" && route !== "mfa-enroll");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string>();
  const [provisioningUri, setProvisioningUri] = useState<string>();
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>();
  const [acknowledgedCodes, setAcknowledgedCodes] = useState(false);

  useEffect(() => {
    if (route === "setup") {
      void request<BootstrapStatus>("/auth/bootstrap-status")
        .then(({ response, result }) => {
          if (!response.ok || !result.bootstrap_available) {
            router.replace("/sign-in?reason=setup-unavailable");
            return;
          }
          setReady(true);
        })
        .catch(() => router.replace("/sign-in?reason=setup-unavailable"));
      return;
    }

    if (route === "mfa-enroll") {
      void request<EnrollmentResult>("/auth/mfa/enroll", {})
        .then(({ response, result }) => {
          if (!response.ok) {
            router.replace("/sign-in?reason=mfa-enrollment-required");
            return;
          }
          setProvisioningUri(result.provisioning_uri);
          setReady(true);
        })
        .catch(() => router.replace("/sign-in?reason=mfa-enrollment-required"));
    }
  }, [route, router]);

  function continueAfterAuthentication(result: LoginResult): void {
    if (result.status === "MFA_ENROLLMENT_REQUIRED") {
      router.replace("/mfa/enroll");
      return;
    }
    if (result.status === "MFA_REQUIRED") {
      router.replace("/mfa/verify");
      return;
    }
    router.replace("/command-center");
  }

  async function submitCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = form.get("email");
    const password = form.get("password");
    const confirmation = form.get("password-confirmation");
    if (typeof email !== "string" || typeof password !== "string") return;
    if (route === "setup" && password !== confirmation) {
      setMessage("Password confirmation does not match.");
      return;
    }

    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const { response, result } = await request<LoginResult>(
        route === "setup" ? "/auth/bootstrap" : "/auth/login",
        { email, password }
      );
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      continueAfterAuthentication(result);
    } catch {
      setMessage("The authentication service is unavailable. Check that the API and HTTPS proxy are running.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitMfaCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    if (typeof code !== "string") return;
    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const path = route === "mfa-enroll" ? "/auth/mfa/enroll/verify" : "/auth/mfa/verify";
      const { response, result } = await request<LoginResult>(path, { code });
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      if (route === "mfa-enroll" && result.recovery_codes) {
        setRecoveryCodes(result.recovery_codes);
        return;
      }
      continueAfterAuthentication(result);
    } catch {
      setMessage("The authentication service is unavailable. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitRecoveryCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const recovery_code = new FormData(event.currentTarget).get("recovery-code");
    if (typeof recovery_code !== "string") return;
    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const { response, result } = await request<LoginResult>("/auth/mfa/recovery", { recovery_code });
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      continueAfterAuthentication(result);
    } catch {
      setMessage("The authentication service is unavailable. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function requestPasswordReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = new FormData(event.currentTarget).get("email");
    if (typeof email !== "string") return;
    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const { response, result } = await request<ApiProblem>("/auth/password-reset", { email });
      setMessage(response.ok ? "If the address belongs to a TraderX account, reset instructions are on their way." : errorMessage(result));
    } catch {
      setMessage("The authentication service is unavailable. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function completePasswordReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const reset_token = form.get("reset-token");
    const new_password = form.get("new-password");
    const proofKind = form.get("proof-kind");
    const proofValue = form.get("proof-value");
    if (
      typeof reset_token !== "string" ||
      typeof new_password !== "string" ||
      typeof proofValue !== "string"
    ) return;

    const proof = proofKind === "recovery" ? { recovery_code: proofValue } : { code: proofValue };
    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const { response, result } = await request<LoginResult>("/auth/password-reset/complete", {
        reset_token,
        new_password,
        proof
      });
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      continueAfterAuthentication(result);
    } catch {
      setMessage("The authentication service is unavailable. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!ready) return <AuthFrame route={route}><section className="auth-card"><p className="status-message" role="status">Checking the authentication step…</p></section></AuthFrame>;

  if (route === "setup" || route === "sign-in") {
    const isSetup = route === "setup";
    return (
      <AuthFrame route={route}>
      <section className="auth-card" aria-labelledby="authentication-heading">
        <h1 id="authentication-heading">{isSetup ? "Set up the initial owner" : "Sign in to TraderX"}</h1>
        <p>{isSetup ? "Initial setup is available exactly once. Later users are invited by an authorized owner." : "Authenticate to access the Command Center."}</p>
        <form className="auth-form" onSubmit={submitCredentials} aria-label={isSetup ? "Initial owner setup" : "TraderX sign in"}>
          <label htmlFor="email">Email</label>
          <input autoComplete="email" id="email" name="email" required type="email" />
          <label htmlFor="password">Password</label>
          <input aria-describedby={isSetup ? "password-hint" : undefined} autoComplete={isSetup ? "new-password" : "current-password"} id="password" minLength={12} name="password" required type="password" />
          {isSetup ? <p className="field-hint" id="password-hint">Use a unique passphrase with at least 12 characters.</p> : null}
          {isSetup ? <><label htmlFor="password-confirmation">Confirm password</label><input autoComplete="new-password" id="password-confirmation" minLength={12} name="password-confirmation" required type="password" /></> : null}
          <button disabled={isSubmitting} type="submit">{isSubmitting ? "Working…" : isSetup ? "Create owner account" : "Sign in"}</button>
        </form>
        {isSetup ? <p className="route-note">Already have an account? <Link href="/sign-in">Sign in instead</Link></p> : <p className="route-note"><Link href="/password-reset">Reset your password</Link></p>}
        <StatusMessage message={message ?? notice} tone={message ? "error" : "info"} />
      </section>
      </AuthFrame>
    );
  }

  if (route === "mfa-enroll") {
    if (recoveryCodes) {
      return (
        <AuthFrame route={route}>
        <section className="auth-card" aria-labelledby="recovery-codes-heading">
          <h1 id="recovery-codes-heading">Save your recovery codes</h1>
          <p>Each code works once if your authenticator is unavailable. They will not be shown again.</p>
          <ul className="recovery-codes">{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
          <label className="confirmation-check"><input checked={acknowledgedCodes} onChange={(event) => setAcknowledgedCodes(event.target.checked)} type="checkbox" /> <span>I have saved these codes securely.</span></label>
          <button disabled={!acknowledgedCodes} onClick={() => router.replace("/command-center")} type="button">Open Command Center</button>
        </section>
        </AuthFrame>
      );
    }
    const setupKey = provisioningUri ? new URL(provisioningUri).searchParams.get("secret") : undefined;
    return (
      <AuthFrame route={route}>
      <section className="auth-card" aria-labelledby="mfa-enrollment-heading">
        <h1 id="mfa-enrollment-heading">Set up your authenticator</h1>
        <p>Enter this setup key in a TOTP authenticator. Do not share it.</p>
        <output aria-label="Authenticator setup key">{setupKey}</output>
        <details><summary>Advanced setup URI</summary><textarea aria-label="Authenticator setup URI" readOnly value={provisioningUri ?? ""} /></details>
        <MfaCodeForm isSubmitting={isSubmitting} message={message} onSubmit={submitMfaCode} submitLabel="Verify and continue" />
      </section>
      </AuthFrame>
    );
  }

  if (route === "mfa-verify") {
    return (
      <AuthFrame route={route}>
      <section className="auth-card" aria-labelledby="mfa-verification-heading">
        <h1 id="mfa-verification-heading">Verify your identity</h1>
        <MfaCodeForm isSubmitting={isSubmitting} message={message} onSubmit={submitMfaCode} submitLabel="Verify and continue" />
        <p className="route-note"><Link href="/mfa-recovery">Use a recovery code</Link></p>
      </section>
      </AuthFrame>
    );
  }

  if (route === "mfa-recovery") {
    return (
      <AuthFrame route={route}>
      <section className="auth-card" aria-labelledby="mfa-recovery-heading">
        <h1 id="mfa-recovery-heading">Recover your authenticator</h1>
        <p>Recovery removes your existing authenticator and requires fresh enrollment.</p>
        <form className="auth-form" onSubmit={submitRecoveryCode} aria-label="MFA recovery">
          <label htmlFor="recovery-code">Recovery code</label>
          <input autoComplete="one-time-code" id="recovery-code" minLength={12} name="recovery-code" required type="text" />
          <button disabled={isSubmitting} type="submit">{isSubmitting ? "Recovering…" : "Recover and enroll again"}</button>
        </form>
        <p className="route-note"><Link href="/sign-in">Return to sign in</Link></p>
        <StatusMessage message={message} tone="error" />
      </section>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame route={route}>
    <section className="auth-card" aria-labelledby="password-reset-heading">
      <h1 id="password-reset-heading">Reset your password</h1>
      <form className="auth-form" onSubmit={requestPasswordReset} aria-label="Request password reset">
        <label htmlFor="reset-email">Email</label>
        <input autoComplete="email" id="reset-email" name="email" required type="email" />
        <button disabled={isSubmitting} type="submit">Send reset instructions</button>
      </form>
      <h2>Complete a password reset</h2>
      <p>A reset link changes your password only. Verify with your authenticator or a recovery code before access is restored.</p>
      <form className="auth-form" onSubmit={completePasswordReset} aria-label="Complete password reset">
        <label htmlFor="reset-token">Reset token</label>
        <input autoComplete="off" id="reset-token" name="reset-token" required type="text" />
        <label htmlFor="new-password">New password</label>
        <input autoComplete="new-password" id="new-password" minLength={12} name="new-password" required type="password" />
        <label htmlFor="proof-kind">Verification method</label>
        <select defaultValue="totp" id="proof-kind" name="proof-kind"><option value="totp">Authenticator code</option><option value="recovery">Recovery code</option></select>
        <label htmlFor="proof-value">Verification code</label>
        <input autoComplete="one-time-code" id="proof-value" name="proof-value" required type="text" />
        <button disabled={isSubmitting} type="submit">{isSubmitting ? "Resetting…" : "Reset password"}</button>
      </form>
      <p className="route-note"><Link href="/sign-in">Return to sign in</Link></p>
      <StatusMessage message={message} tone="error" />
    </section>
    </AuthFrame>
  );
}

function MfaCodeForm({ isSubmitting, message, onSubmit, submitLabel }: { isSubmitting: boolean; message?: string; onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>; submitLabel: string }) {
  return (
    <form className="auth-form" onSubmit={onSubmit} aria-label="TraderX multi-factor verification">
      <label htmlFor="mfa-code">Authenticator code</label>
      <input autoComplete="one-time-code" id="mfa-code" inputMode="numeric" name="code" pattern="[0-9]{6}" required type="text" />
      <button disabled={isSubmitting} type="submit">{isSubmitting ? "Verifying…" : submitLabel}</button>
      <StatusMessage message={message} tone="error" />
    </form>
  );
}
