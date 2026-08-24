"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { api, ApiError, API_ROOT } from "@/lib/api";

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
  useEffect(() => {
    if (!isAuthPage && auth.error instanceof ApiError && auth.error.status === 401) {
      router.replace("/auth" as Route);
    }
    if (isAuthPage && auth.data) router.replace("/");
  }, [auth.data, auth.error, isAuthPage, router]);

  const logout = async () => {
    await api<void>("/auth/sessions", { method: "DELETE" });
    await auth.refetch();
    router.replace("/auth" as Route);
  };

  if (!isAuthPage && auth.isPending) return <div className="center-state">Checking secure session…</div>;
  if (!isAuthPage && !auth.data) return <div className="center-state">Sign-in required…</div>;
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
