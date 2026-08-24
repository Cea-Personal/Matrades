"use client";

import { useAuth } from "@/lib/providers";

export function SessionMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="session-menu">
      <span>{user.email}</span>
      <small>{user.role}</small>
      <button className="btn compact" onClick={() => void logout()}>
        Sign out
      </button>
    </div>
  );
}

