"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/providers";

type SignupState = {
  verification_token: string;
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
  const [code, setCode] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [enrollment, setEnrollment] = useState<EnrollmentState | null>(null);
  const [challengeId, setChallengeId] = useState("");
  const [recoveryToken, setRecoveryToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  const begin = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      if (mode === "recovery") {
        const result = await api<{ recovery_token?: string }>("/auth/password-recovery", {
          method: "POST",
          body: JSON.stringify({ email }),
        });
        setRecoveryToken(result.recovery_token ?? "sent-by-email");
      } else if (mode === "signup") {
        const result = await api<SignupState>("/auth/signup", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setVerificationToken(result.verification_token ?? "");
      } else {
        const result = await api<{ challenge_id: string }>("/auth/sessions", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setChallengeId(result.challenge_id);
      }
    });
  };

  const verifyEmail = () =>
    run(async () => {
      const result = await api<VerificationState>("/auth/email-verifications", {
        method: "POST",
        body: JSON.stringify({ token: verificationToken }),
      });
      const created = await api<EnrollmentState>("/auth/mfa/enrollments", {
        method: "POST",
        headers: { "X-Enrollment-Token": result.enrollment_token },
      });
      setEnrollment(created);
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
        <p className="muted">Verified email and an authenticator challenge protect trading configuration.</p>
        {!verificationToken && !challengeId && !enrollment && !recoveryToken && (
          <form onSubmit={begin} className="form-stack">
            <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {mode !== "recovery" && <label>Password<input type="password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>}
            <button className="btn primary" disabled={busy}>{busy ? "Working…" : mode === "login" ? "Continue to MFA" : mode === "signup" ? "Create account" : "Send recovery link"}</button>
          </form>
        )}
        {mode === "recovery" && recoveryToken && (
          <div className="form-stack">
            <p className="muted">Enter the one-time token delivered to your verified email. Development mode displays it below.</p>
            <label>Recovery token<input required value={recoveryToken} onChange={(e) => setRecoveryToken(e.target.value)} /></label>
            <label>New password<input type="password" minLength={12} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
            <button className="btn primary" disabled={busy || newPassword.length < 12} onClick={() => void completeRecovery()}>Reset password and revoke sessions</button>
          </div>
        )}
        {verificationToken && !enrollment && (
          <div className="form-stack">
            <p>Email delivery is in development mode. Use the generated one-time verification token.</p>
            <label>Verification token<textarea value={verificationToken} onChange={(e) => setVerificationToken(e.target.value)} /></label>
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
        {!verificationToken && !challengeId && !enrollment && !recoveryToken && (
          <div className="actions">
            <button className="text-button" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
              {mode === "login" ? "Need an account? Sign up" : "Already registered? Sign in"}
            </button>
            {mode === "login" && <button className="text-button" onClick={() => setMode("recovery")}>Forgot password?</button>}
          </div>
        )}
      </div>
    </section>
  );
}
