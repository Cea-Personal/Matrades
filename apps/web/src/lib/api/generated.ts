/* Generated contract boundary. Regenerate from specs/.../contracts/http-api.yaml. */
export type DecimalString = string;
export type RiskState = "NORMAL" | "CAUTION" | "DEFENSIVE" | "LOCKDOWN";
export type RiskDecision = "PASS" | "PASS_REDUCED" | "BLOCKED";
export type MarketCategory = "COMMODITY" | "FOREX" | "CRYPTO";
export type SourceSemantics = "AUTHORITATIVE" | "ACTUAL" | "BROKER_PROXY" | "UNAVAILABLE";

export interface MarketResearchSchedule {
  id?: string;
  account_id?: string;
  interval_seconds?: number;
  anchored_start_local?: string;
  account_timezone?: string;
  enabled: boolean;
  next_run_at?: string;
  last_due_at?: string | null;
  version?: number;
  configured?: boolean;
}

export interface MarketResearchModelConfiguration {
  id?: string;
  llm_integration_id?: string;
  provider_key?: "OPENAI_RESPONSES" | "ANTHROPIC_MESSAGES";
  exact_model_id?: string;
  catalogue_revision?: string;
  applies_to: "FUTURE_RUNS_ONLY";
  configured?: boolean;
}

export interface MarketSourceEvidence {
  provider: string;
  venue?: string | null;
  capability: string;
  semantics: SourceSemantics;
  source_role: string;
  freshness: string;
  age_seconds?: number | null;
  freshness_policy_version?: string;
  mapping_revision?: string | null;
  conflict_state?: string;
}

export interface CoordinatedCategoryReport {
  run_id: string;
  category: MarketCategory;
  state: string;
  outcome: string;
  block_reasons: string[];
  source_manifest: { evidence?: MarketSourceEvidence[]; selected_role?: string };
  fallback_path: Array<{ role: string; accepted: boolean; reason_codes: string[] }>;
  deterministic_result_hash?: string | null;
  llm_analysis: { state: string; authoritative: false; analysis?: Record<string, unknown> };
  activation_state: string;
  candidates?: Array<Record<string, unknown>>;
}

export interface CoordinatedMarketResearchReport {
  id: string;
  state: string;
  trigger: string;
  methodology_version: string;
  source_catalogue_revision: string;
  exact_model_id?: string | null;
  categories: CoordinatedCategoryReport[];
  ranking_is_not_activation: true;
  active_assignments_changed: false;
}

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

  async send<T>(path: string, method: "POST" | "PUT" | "DELETE", body: object, headers: Record<string, string> = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw (await response.json()) as ApiProblem;
    return response.json() as Promise<T>;
  }
}
