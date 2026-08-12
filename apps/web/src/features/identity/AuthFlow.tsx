"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type LoginStatus = "AUTHENTICATED" | "MFA_ENROLLMENT_REQUIRED" | "MFA_REQUIRED";
type Stage = "credentials" | "enroll" | "verify" | "recovery";

type LoginResult = {
  status: LoginStatus;
  recovery_codes?: string[];
};

type EnrollmentResult = {
  provisioning_uri: string;
};

type ApiProblem = {
  detail?: string;
  title?: string;
};

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

export function AuthFlow() {
  const router = useRouter();
  const [bootstrapAvailable, setBootstrapAvailable] = useState(true);
  const [isBootstrap, setIsBootstrap] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string>();
  const [provisioningUri, setProvisioningUri] = useState<string>();
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>();
  const [stage, setStage] = useState<Stage>("credentials");

  useEffect(() => {
    void request<{ bootstrap_available: boolean }>("/auth/bootstrap-status").then(({ response, result }) => {
      if (response.ok) setBootstrapAvailable(result.bootstrap_available);
    }).catch(() => undefined);
  }, []);

  async function beginMfaEnrollment() {
    const { response, result } = await request<EnrollmentResult>("/auth/mfa/enroll", {});
    if (!response.ok) {
      setMessage(errorMessage(result));
      return;
    }
    setProvisioningUri(result.provisioning_uri);
    setMessage("Add this account to your authenticator, then enter its current six-digit code.");
    setStage("enroll");
  }

  async function handleLoginResult(result: LoginResult) {
    if (result.status === "MFA_ENROLLMENT_REQUIRED") {
      await beginMfaEnrollment();
      return;
    }
    if (result.status === "MFA_REQUIRED") {
      setMessage("Enter the current six-digit code from your authenticator.");
      setStage("verify");
      return;
    }
    setRecoveryCodes(result.recovery_codes);
    setMessage(result.recovery_codes ? "Save these recovery codes somewhere safe. They are shown only once." : undefined);
    setStage(result.recovery_codes ? "recovery" : "verify");
    if (!result.recovery_codes) router.replace("/command-center");
  }

  async function submitCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = form.get("email");
    const password = form.get("password");
    const confirmation = form.get("password-confirmation");
    if (typeof email !== "string" || typeof password !== "string") return;
    if (isBootstrap && password !== confirmation) {
      setMessage("Password confirmation does not match.");
      return;
    }

    setIsSubmitting(true);
    setMessage(undefined);
    try {
      const { response, result } = await request<LoginResult>(
        isBootstrap ? "/auth/bootstrap" : "/auth/login",
        { email, password }
      );
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      await handleLoginResult(result);
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
      const path = stage === "enroll" ? "/auth/mfa/enroll/verify" : "/auth/mfa/verify";
      const { response, result } = await request<LoginResult>(path, { code });
      if (!response.ok) {
        setMessage(errorMessage(result));
        return;
      }
      await handleLoginResult(result);
    } catch {
      setMessage("The authentication service is unavailable. Check that the API and HTTPS proxy are running.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (stage === "recovery") {
    return (
      <section aria-labelledby="recovery-codes">
        <h2 id="recovery-codes">Save your recovery codes</h2>
        <p>Each code works once if your authenticator is unavailable.</p>
        <ul>{recoveryCodes?.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
        <button onClick={() => router.replace("/command-center")} type="button">Open Command Center</button>
        {message && <p role="status">{message}</p>}
      </section>
    );
  }

  if (stage === "enroll" || stage === "verify") {
    const setupKey = provisioningUri ? new URL(provisioningUri).searchParams.get("secret") : undefined;
    return (
      <section aria-labelledby="mfa-challenge">
        <h2 id="mfa-challenge">{stage === "enroll" ? "Set up your authenticator" : "Verify your identity"}</h2>
        {stage === "enroll" && provisioningUri && <>
          <p>Enter this setup key in your TOTP authenticator. Do not share it.</p>
          <output aria-label="Authenticator setup key">{setupKey}</output>
          <details><summary>Advanced setup URI</summary><textarea aria-label="Authenticator setup URI" readOnly value={provisioningUri} /></details>
        </>}
        <form onSubmit={submitMfaCode} aria-label="TraderX multi-factor verification">
          <label htmlFor="mfa-code">Authenticator code</label>
          <input autoComplete="one-time-code" id="mfa-code" inputMode="numeric" name="code" pattern="[0-9]{6}" required type="text" />
          <button disabled={isSubmitting} type="submit">{isSubmitting ? "Verifying…" : "Verify and continue"}</button>
        </form>
        {message && <p role="status">{message}</p>}
      </section>
    );
  }

  return (
    <section aria-labelledby="authentication-heading">
      <h2 id="authentication-heading">{isBootstrap ? "Set up the initial owner" : "Sign in"}</h2>
      <form onSubmit={submitCredentials} aria-label="TraderX sign in">
        <label htmlFor="email">Email</label>
        <input autoComplete="email" id="email" name="email" required type="email" />
        <label htmlFor="password">Password</label>
        <input autoComplete={isBootstrap ? "new-password" : "current-password"} id="password" minLength={12} name="password" required type="password" />
        {isBootstrap && <><label htmlFor="password-confirmation">Confirm password</label><input autoComplete="new-password" id="password-confirmation" minLength={12} name="password-confirmation" required type="password" /></>}
        <button disabled={isSubmitting} type="submit">{isSubmitting ? "Working…" : isBootstrap ? "Create owner account" : "Sign in"}</button>
      </form>
      {bootstrapAvailable && <button onClick={() => { setIsBootstrap(!isBootstrap); setMessage(undefined); }} type="button">{isBootstrap ? "I already have an account" : "Set up the initial owner"}</button>}
      {isBootstrap && <p>Initial setup is available only once. All later users must be invited by an authorized owner.</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
