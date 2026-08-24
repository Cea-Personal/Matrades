export const API_ROOT = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (typeof window !== "undefined" && !headers.has("Step-Up-Grant")) {
    const grant = window.sessionStorage.getItem("matrades_step_up");
    if (grant) headers.set("Step-Up-Grant", grant);
  }
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown; message?: unknown };
      detail = body.detail ?? body.message ?? body;
    } catch {
      detail = await response.text();
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type Resource = {
  id: string;
  owner_id: string;
  kind: string;
  state: string;
  version: number;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
};
