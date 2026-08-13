"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { CommandCenter } from "./CommandCenter";

type Dashboard = {
  risk: { state: string; capacity: number };
};

export function AuthenticatedCommandCenter() {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    void fetch("/api/v1/dashboard", { credentials: "same-origin" }).then(async (response) => {
      if (response.status === 401) {
        router.replace("/sign-in?reason=session-expired");
        return;
      }
      if (!response.ok) {
        setError("The Command Center is unavailable. Please try again.");
        return;
      }
      setDashboard(await response.json() as Dashboard);
    }).catch(() => setError("The Command Center is unavailable. Please try again."));
  }, [router]);

  if (error) return <p role="alert">{error}</p>;
  if (!dashboard) return <p role="status">Loading Command Center…</p>;
  return <CommandCenter capacity={dashboard.risk.capacity} state={dashboard.risk.state} />;
}
