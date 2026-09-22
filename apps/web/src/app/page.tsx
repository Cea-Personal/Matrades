"use client";

import { OverviewDashboard } from "@/features/overview/OverviewDashboard";

import { useAuth } from "@/lib/providers";

export default function Dashboard() {
  const { user } = useAuth();
  return user ? <OverviewDashboard /> : null;
}
