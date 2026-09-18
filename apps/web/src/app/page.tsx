"use client";

import { useEffect } from "react";

import { useRouter } from "next/navigation";

import { OverviewDashboard } from "@/features/overview/OverviewDashboard";

import { useAuth } from "@/lib/providers";

export default function Dashboard() {

  const router = useRouter();

  const { user } = useAuth();

  useEffect(() => {

    if (!user) {

      router.replace("/auth");

    }

  }, [user, router]);

  if (!user) {

    return null;

  }

  return <OverviewDashboard />;

}