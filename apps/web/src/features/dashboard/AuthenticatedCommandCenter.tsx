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
    const refreshDashboard = () => {
      void loadDashboard();
    };
    // Defer the initial request so this effect only establishes the external
    // fetch. Workspace mutations can also request a dashboard refresh without
    // remounting the current workspace.
    void Promise.resolve().then(loadDashboard);
    window.addEventListener("traderx:dashboard-refresh", refreshDashboard);
    return () => window.removeEventListener("traderx:dashboard-refresh", refreshDashboard);
  }, [loadDashboard]);

  if (error) return <p role="alert">{error}</p>;
  if (!dashboard) return <p role="status">Loading Command Center…</p>;
  return <CommandCenter dashboard={dashboard} onAccountChanged={loadDashboard} />;
}
