"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function SessionNavigation() {
  const router = useRouter();
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function signOut() {
    setIsSigningOut(true);
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "same-origin"
      });
    } finally {
      router.replace("/");
      router.refresh();
      setIsSigningOut(false);
    }
  }

  return (
    <nav aria-label="Primary navigation" className="session-navigation">
      <Link href="/command-center">Command Center</Link>
      <button disabled={isSigningOut} onClick={signOut} type="button">
        {isSigningOut ? "Signing out…" : "Log out"}
      </button>
    </nav>
  );
}
