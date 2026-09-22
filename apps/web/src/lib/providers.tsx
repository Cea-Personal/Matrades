"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { api, API_ROOT } from "@/lib/api";

export type CurrentUser = {
  id: string;
  owner_id: string;
  email: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  role: string;
};

type AuthContextValue = {
  user: CurrentUser | null;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function RealtimeInvalidator() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const stream = new EventSource(`${API_ROOT}/events`, { withCredentials: true });
    const invalidate = () => { void queryClient.invalidateQueries(); };
    stream.addEventListener("domain", invalidate);
    return () => {
      stream.removeEventListener("domain", invalidate);
      stream.close();
    };
  }, [queryClient]);
  return null;
}

function QueryFailureBanner() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  useEffect(
    () =>
      queryClient.getQueryCache().subscribe(() => {
        const failure = queryClient
          .getQueryCache()
          .getAll()
          .find((query) => query.state.status === "error");
        const error = failure?.state.error;
        setMessage(error instanceof Error ? error.message : error ? "Live data is unavailable" : "");
      }),
    [queryClient],
  );
  return message ? <div className="global-error" role="alert">Live data degraded: {message}</div> : null;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must run inside AppProviders");
  return value;
}

function AuthBoundary({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useQuery<CurrentUser>({
    queryKey: ["auth", "me"],
    queryFn: () => api("/auth/me"),
    retry: false,
    staleTime: 30_000,
  });
  const isAuthPage = pathname === "/auth";
  const requiresAuthentication = !isAuthPage && !auth.isPending && !auth.data;
  useEffect(() => {
    // A signed-out visit should land on the existing login/sign-up screen.
    // Keep this independent of the exact API error payload so expired sessions
    // and gateway-shaped 401 responses behave the same way.
    if (requiresAuthentication) {
      router.replace("/auth" as Route);
    }
    if (isAuthPage && auth.data) router.replace("/");
  }, [auth.data, isAuthPage, requiresAuthentication, router]);

  const logout = async () => {
    await api<void>("/auth/sessions", { method: "DELETE" });
    await auth.refetch();
    router.replace("/auth" as Route);
  };

  // Do not render a sign-in or sign-up placeholder on protected routes. The
  // redirect above owns the signed-out transition; /auth owns authentication.
  if (!isAuthPage && auth.isPending) return null;
  if (requiresAuthentication) return null;
  return (
    <AuthContext.Provider value={{ user: auth.data ?? null, refresh: auth.refetch, logout }}>
      {auth.data && <RealtimeInvalidator />}
      {auth.data && <QueryFailureBanner />}
      {children}
    </AuthContext.Provider>
  );
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthBoundary>{children}</AuthBoundary>
    </QueryClientProvider>
  );
}
