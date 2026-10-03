"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/providers";

type SignupState = {
  verification_token?: string;
  enrollment_token?: string;
};

type VerificationState = {
  enrollment_token: string;
};

type EnrollmentState = {
  enrollment_id: string;
  secret: string;
  setup_uri: string;
  recovery_codes: string[];
};

export default function AuthenticationPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [mode, setMode] = useState<"login" | "signup" | "recovery">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [code, setCode] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [awaitingEmail, setAwaitingEmail] = useState(false);
  const [recoverySent, setRecoverySent] = useState(false);
  const [signupAvailable, setSignupAvailable] = useState(false);
  const [emailVerificationEnabled, setEmailVerificationEnabled] = useState(false);
  const [setupCodeRequired, setSetupCodeRequired] = useState(false);
  const [enrollment, setEnrollment] = useState<EnrollmentState | null>(null);
  const [challengeId, setChallengeId] = useState("");
  const [recoveryToken, setRecoveryToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api<{ signup_available: boolean; email_verification_enabled: boolean; setup_code_required: boolean }>("/auth/registration-status")
      .then(result => {
        if (!active) return;
        setSignupAvailable(result.signup_available);
        setEmailVerificationEnabled(result.email_verification_enabled);
        setSetupCodeRequired(result.setup_code_required);
      })
      .catch(() => { if (active) setSignupAvailable(false); });
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const verification = fragment.get("verify");
    const recovery = fragment.get("recover");
    const fragmentTimer = window.setTimeout(() => {
      if (!active) return;
      if (verification) setVerificationToken(verification);
      if (recovery) { setMode("recovery"); setRecoveryToken(recovery); }
      if (verification || recovery) window.history.replaceState(null, "", window.location.pathname);
    }, 0);
    return () => { active = false; window.clearTimeout(fragmentTimer); };
  }, []);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const startEnrollment = async (token: string) => {
    const created = await api<EnrollmentState>("/auth/mfa/enrollments", {
      method: "POST",
      headers: { "X-Enrollment-Token": token },
    });
    setEnrollment(created);
    setAwaitingEmail(false);
  };

  const begin = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      if (mode === "recovery") {
        const result = await api<{ recovery_token?: string }>("/auth/password-recovery", {
          method: "POST",
          body: JSON.stringify({ email }),
        });
        if (result.recovery_token) setRecoveryToken(result.recovery_token);
        else setRecoverySent(true);
      } else if (mode === "signup") {
        const result = await api<SignupState>("/auth/signup", {
          method: "POST",
          body: JSON.stringify({ email, password, setup_code: setupCode || undefined }),
        });
        if (result.enrollment_token) await startEnrollment(result.enrollment_token);
        else if (result.verification_token) setVerificationToken(result.verification_token);
        else setAwaitingEmail(true);
        setSignupAvailable(false);
      } else {
        const result = await api<{ challenge_id?: string; enrollment_token?: string }>("/auth/sessions", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        if (result.enrollment_token) await startEnrollment(result.enrollment_token);
        else if (result.challenge_id) setChallengeId(result.challenge_id);
      }
    });
  };

  const verifyEmail = () =>
    run(async () => {
      const result = await api<VerificationState>("/auth/email-verifications", {
        method: "POST",
        body: JSON.stringify({ token: verificationToken }),
      });
      await startEnrollment(result.enrollment_token);
    });

  const resendVerification = () =>
    run(async () => {
      const result = await api<{ verification_token?: string }>("/auth/email-verifications/resend", {
        method: "POST", body: JSON.stringify({ email }),
      });
      if (result.verification_token) setVerificationToken(result.verification_token);
      else setAwaitingEmail(true);
    });

  const completeMfa = () =>
    run(async () => {
      if (enrollment) {
        await api("/auth/mfa/enrollments/confirm", {
          method: "POST",
          body: JSON.stringify({ enrollment_id: enrollment.enrollment_id, code }),
        });
      } else {
        await api("/auth/mfa/challenges", {
          method: "POST",
          body: JSON.stringify({ challenge_id: challengeId, code }),
        });
      }
      await refresh();
      router.replace("/");
    });

  const completeRecovery = () =>
    run(async () => {
      await api("/auth/password-recovery/complete", {
        method: "POST",
        body: JSON.stringify({ token: recoveryToken, new_password: newPassword }),
      });
      setRecoveryToken("");
      setNewPassword("");
      setPassword("");
      setMode("login");
    });

  return (
    <section className="auth-page">
      <div className="auth-card">
        <p className="eyebrow">Secure workspace</p>
        <h1>{mode === "login" ? "Sign in to Matrades" : mode === "signup" ? "Create your Matrades account" : "Recover your account"}</h1>
        <p className="muted">{emailVerificationEnabled ? "Verified email and an authenticator challenge protect trading configuration." : "An authenticator challenge protects trading configuration."}</p>
        {!verificationToken && !challengeId && !enrollment && !recoveryToken && !awaitingEmail && !recoverySent && (
          <form onSubmit={begin} className="form-stack">
            <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {mode !== "recovery" && <label>Password<input type="password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>}
            {mode === "signup" && setupCodeRequired && <label>Owner setup code<input type="password" required value={setupCode} onChange={(e) => setSetupCode(e.target.value)} /></label>}
            <button className="btn primary" disabled={busy}>{busy ? "Working…" : mode === "login" ? "Continue to MFA" : mode === "signup" ? "Create account" : "Send recovery link"}</button>
          </form>
        )}
        {mode === "recovery" && recoverySent && !recoveryToken && (
          <div className="form-stack">
            <p>Check your email for a one-time password-reset link. It expires after 30 minutes.</p>
            <button className="text-button" onClick={() => { setRecoverySent(false); setMode("login"); }}>Return to sign in</button>
          </div>
        )}
        {mode === "recovery" && recoveryToken && (
          <div className="form-stack">
            <p className="muted">Enter the one-time token from your password-reset email.</p>
            <label>Recovery token<input required value={recoveryToken} onChange={(e) => setRecoveryToken(e.target.value)} /></label>
            <label>New password<input type="password" minLength={12} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
            <button className="btn primary" disabled={busy || newPassword.length < 12} onClick={() => void completeRecovery()}>Reset password and revoke sessions</button>
          </div>
        )}
        {awaitingEmail && !verificationToken && (
          <div className="form-stack">
            <p>Check your email for a verification link. It expires after 24 hours.</p>
            <label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} /></label>
            <button className="btn" disabled={busy || !email} onClick={() => void resendVerification()}>Resend verification email</button>
            <button className="text-button" onClick={() => { setAwaitingEmail(false); setMode("login"); }}>Return to sign in</button>
          </div>
        )}
        {verificationToken && !enrollment && (
          <div className="form-stack">
            <p>Confirm your email and set up an authenticator.</p>
            <label>Verification token<input value={verificationToken} onChange={(e) => setVerificationToken(e.target.value)} /></label>
            <button className="btn primary" disabled={busy} onClick={() => void verifyEmail()}>Verify and enroll MFA</button>
          </div>
        )}
        {enrollment && (
          <div className="form-stack">
            <div className="notice warn"><strong>Save these recovery codes once.</strong><code>{enrollment.recovery_codes.join("\n")}</code></div>
            <label>Authenticator secret<input readOnly value={enrollment.secret} /></label>
            <label>6-digit authenticator code<input inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} /></label>
            <button className="btn primary" disabled={busy || code.length !== 6} onClick={() => void completeMfa()}>Activate MFA</button>
          </div>
        )}
        {challengeId && (
          <div className="form-stack">
            <label>Authenticator or recovery code<input autoFocus value={code} onChange={(e) => setCode(e.target.value)} /></label>
            <button className="btn primary" disabled={busy || code.length < 6} onClick={() => void completeMfa()}>Sign in securely</button>
          </div>
        )}
        {error && <p className="notice bad" role="alert">{error}</p>}
        {!verificationToken && !challengeId && !enrollment && !recoveryToken && !awaitingEmail && !recoverySent && (
          <div className="actions">
            {(mode !== "login" || signupAvailable) && <button className="text-button" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
              {mode === "login" ? "Set up the owner account" : "Already registered? Sign in"}
            </button>}
            {mode === "login" && <button className="text-button" onClick={() => setMode("recovery")}>Forgot password?</button>}
            {mode === "login" && emailVerificationEnabled && !signupAvailable && error.includes("email verification and MFA") && <button className="text-button" onClick={() => { setError(""); setAwaitingEmail(true); }}>Resend verification link</button>}
          </div>
        )}
      </div>
    </section>
  );
}
