/** Generated contract marker. Regenerate from contracts/openapi.yaml. */
export const CONTRACT_VERSION = "matrades.openapi.v1" as const;
export type AssetClass = "FOREX" | "METALS" | "CRYPTOCURRENCY" | "STOCKS";
export type InstrumentType = "SPOT" | "CFD" | "FUTURES";
export type QuantityUnit = "UNITS" | "SHARES" | "LOTS" | "CONTRACTS";
export type ResearchLaneKey = { asset_class: AssetClass; instrument_type: InstrumentType };
export type ResearchLaneResult = { lane: ResearchLaneKey; status: string; reason_code?: string; source_cut_refs: string[] };
export type RuntimeType = "CODEX_APP_SERVER" | "LITELLM_GATEWAY";
export type HealthStatus = "HEALTHY" | "DEGRADED" | "STALE" | "OFFLINE" | "DISABLED" | "UNTESTED";
