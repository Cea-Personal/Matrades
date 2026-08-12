/* Generated contract boundary. Regenerate from specs/.../contracts/http-api.yaml. */
export type DecimalString = string;
export type RiskState = "NORMAL" | "CAUTION" | "DEFENSIVE" | "LOCKDOWN";
export type RiskDecision = "PASS" | "PASS_REDUCED" | "BLOCKED";

export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  correlation_id: string;
}

export class ApiClient {
  constructor(private readonly baseUrl = process.env.NEXT_PUBLIC_TRADERX_API_BASE ?? "/api/v1") {}

  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, { credentials: "same-origin" });
    if (!response.ok) throw (await response.json()) as ApiProblem;
    return response.json() as Promise<T>;
  }
}
