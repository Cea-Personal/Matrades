/* Generated contract boundary. Regenerate from specs/.../contracts/http-api.yaml. */
export type DecimalString = string;
export type RiskState = "NORMAL" | "CAUTION" | "DEFENSIVE" | "LOCKDOWN";
export type RiskDecision = "PASS" | "PASS_REDUCED" | "BLOCKED";
export type MarketCategory = "COMMODITY" | "FOREX" | "CRYPTO";
export type SourceSemantics = "AUTHORITATIVE" | "ACTUAL" | "BROKER_PROXY" | "AGGREGATED_PROXY" | "UNAVAILABLE";

export interface EconomicCalendarEvent {
  id: string;
  source_origin: "OFFICIAL_MACHINE" | "OWNER_CITED";
  official_url: string;
  title: string;
  event_type: string;
  importance: "HIGH" | "MEDIUM" | "LOW";
  scheduled_at: string;
  affected_categories: MarketCategory[];
  coverage_state: string;
}

export interface EventRiskPolicy {
  id?: string;
  enabled_event_types: string[];
  pre_event_buffer_seconds: number;
  post_event_buffer_seconds: number;
  required_source_coverage: string[];
  effective_at?: string;
}

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
  provider_key?: "LITELLM_PROXY";
  exact_model_id?: string;
  research_brief?: string;
  catalogue_revision?: string;
  version?: number;
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
  observed_at?: string | null;
  received_at?: string;
  provider_symbol?: string | null;
  canonical_instrument_id?: string | null;
  entitlement_status?: string;
  complete?: boolean;
  quality?: string;
  fallback_reason?: string | null;
  raw_reference?: string | null;
  measures?: Record<string, string>;
}

export interface CoordinatedMarketCandidate {
  id: string;
  instrument_id: string;
  symbol: string;
  display_name: string;
  eligible: boolean;
  score: string | null;
  rank: number | null;
  confidence: string;
  exclusions: string[];
  components: Record<string, string>;
  rationale: Record<string, unknown>;
  source_evidence: MarketSourceEvidence[];
}

export interface AdvisoryAnalysisStatus {
  state: string;
  authoritative: false;
  provider?: string | null;
  exact_model_id?: string | null;
  research_brief?: string | null;
  catalogue_revision?: string | null;
  adapter_revision?: string | null;
  prompt_template_version?: string | null;
  output_schema_version?: string | null;
  inference_policy_version?: string | null;
  attempt_count: number;
  retry_eligible: boolean;
  analysis?: Record<string, unknown> | null;
  failure_reason?: string | null;
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
  policy_pins: Record<string, unknown>;
  llm_analysis: AdvisoryAnalysisStatus;
  activation_state: string;
  candidates: CoordinatedMarketCandidate[];
  selection_proposal: {
    state: "REVIEW_REQUIRED";
    candidate: CoordinatedMarketCandidate;
    active_assignment_changed: false;
  } | null;
}

export interface CoordinatedMarketResearchReport {
  id: string;
  state: string;
  trigger: string;
  methodology_version: string;
  source_catalogue_revision: string;
  exact_model_id?: string | null;
  research_brief?: string | null;
  freshness_policy_manifest: Record<string, string>;
  retry_policy_manifest: Record<string, string>;
  model_pin: {
    provider?: string | null;
    exact_model_id?: string | null;
    catalogue_revision?: string | null;
    adapter_revision?: string | null;
    prompt_template_version?: string | null;
    output_schema_version?: string | null;
    inference_policy_version?: string | null;
    research_brief?: string | null;
  };
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
