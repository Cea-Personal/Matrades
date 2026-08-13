"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { CommandCenter, type Dashboard } from "./CommandCenter";

export function AuthenticatedCommandCenter() {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [error, setError] = useState<string>();

  const loadDashboard = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/dashboard", { credentials: "same-origin" });
      if (response.status === 401) {
        router.replace("/sign-in?reason=session-expired");
        return;
      }
      if (!response.ok) {
        setError("The Command Center is unavailable. Please try again.");
        return;
      }
      setDashboard(await response.json() as Dashboard);
    } catch {
      setError("The Command Center is unavailable. Please try again.");
    }
  }, [router]);

  useEffect(() => {
    // Defer the request to an asynchronous task so this effect only establishes
    // the external fetch, rather than synchronously cascading a state update.
    void Promise.resolve().then(loadDashboard);
  }, [loadDashboard]);

  if (error) return <p role="alert">{error}</p>;
  if (!dashboard) return <p role="status">Loading Command Center…</p>;
  return <CommandCenter dashboard={dashboard} onAccountChanged={loadDashboard} />;
}
