"use client";

import { useState } from "react";

import { useAuth } from "@/lib/providers";

export function SessionMenu() {
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!user) return null;
  const signOut = async () => {
    setBusy(true);
    setError("");
    try {
      await logout();
    } catch {
      setError("Sign-out failed. Please try again.");
      setBusy(false);
    }
  };
  return (
    <div className="session-menu">
      <span>{user.email}</span>
      <small>{user.role}</small>
      <button className="btn compact" disabled={busy} onClick={() => void signOut()}>
        {busy ? "Signing out…" : "Sign out"}
      </button>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
