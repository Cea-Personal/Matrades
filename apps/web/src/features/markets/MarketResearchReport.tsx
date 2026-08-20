import type {
  CoordinatedMarketResearchReport,
  MarketCategory,
  MarketSourceEvidence
} from "@/lib/api/generated";

export type MarketCandidate = {
  id: string;
  instrument_id?: string;
  symbol: string;
  display_name: string;
  eligible: boolean;
  score: string | null;
  rank: number | null;
  confidence: string;
  exclusions: string[];
  components: Record<string, string>;
  rationale?: Record<string, unknown>;
  source_evidence?: MarketSourceEvidence[];
  category?: MarketCategory;
};

type ReportProps = {
  candidates?: MarketCandidate[];
  methodologyVersion?: string;
  coordinated?: CoordinatedMarketResearchReport;
  onRetry?: (runId: string) => void;
  onReview?: (candidate: MarketCandidate) => void;
};

const CATEGORY_LABELS: Record<MarketCategory, string> = {
  COMMODITY: "Commodity",
  FOREX: "Forex",
  CRYPTO: "Cryptocurrency"
};

function readable(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

function reportValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function EvidenceList({ evidence }: { evidence: MarketSourceEvidence[] }) {
  if (!evidence.length) return <p className="workspace-notice">No source evidence was retained.</p>;
  return <dl>{evidence.map((source, index) => <div key={`${source.provider}-${source.capability}-${index}`}><dt>{source.provider} · {source.capability}</dt><dd>{source.semantics} · {source.freshness}{source.venue ? ` · ${source.venue}` : ""}{source.quality ? ` · ${source.quality}` : ""}{source.conflict_state ? ` · ${source.conflict_state}` : ""}{source.measures && Object.keys(source.measures).length ? ` · ${Object.entries(source.measures).map(([key, value]) => `${readable(key)} ${value}`).join(" · ")}` : ""}</dd></div>)}</dl>;
}

function CandidateDetails({ candidate }: { candidate: MarketCandidate }) {
  const components = Object.entries(candidate.components);
  return <article className={candidate.eligible ? "candidate-card candidate-eligible" : "candidate-card candidate-excluded"}><header><div><span>{candidate.rank ? `Rank ${candidate.rank}` : "Excluded"}</span><h5>{candidate.symbol} · {candidate.display_name}</h5></div>{candidate.eligible ? <strong>Score {candidate.score}</strong> : null}</header>{components.length ? <dl>{components.map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{value}</dd></div>)}<div><dt>Confidence</dt><dd>{candidate.confidence}</dd></div></dl> : null}{candidate.exclusions.length ? <p><strong>Failed gates:</strong> {candidate.exclusions.map(readable).join(" · ")}</p> : null}{candidate.rationale ? <details><summary>Deterministic rationale</summary><dl>{Object.entries(candidate.rationale).map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{reportValue(value)}</dd></div>)}</dl></details> : null}</article>;
}

export function MarketResearchReport({ candidates = [], methodologyVersion, coordinated, onRetry, onReview }: ReportProps) {
  if (coordinated) {
    return <section aria-label="Coordinated market research"><header><p className="section-kicker">Immutable coordinated run</p><h3>Three-category research report</h3><p><strong>Ranking is not activation.</strong> The active market is preserved until a separate human confirmation.</p></header><dl className="evidence-metrics"><div><dt>Run state</dt><dd>{coordinated.state}</dd></div><div><dt>Method</dt><dd>{coordinated.methodology_version}</dd></div><div><dt>Pinned model</dt><dd>{coordinated.exact_model_id ?? "No advisory model"}</dd></div><div><dt>Catalogue</dt><dd>{coordinated.source_catalogue_revision}</dd></div></dl><details><summary>Immutable source, model, and policy pins</summary><dl><div><dt>Source freshness policies</dt><dd>{reportValue(coordinated.freshness_policy_manifest)}</dd></div><div><dt>Retry policies</dt><dd>{reportValue(coordinated.retry_policy_manifest)}</dd></div>{Object.entries(coordinated.model_pin).map(([key, value]) => <div key={key}><dt>Model · {readable(key)}</dt><dd>{reportValue(value)}</dd></div>)}</dl></details><div className="candidate-list">{coordinated.categories.map((item) => {
      const label = CATEGORY_LABELS[item.category];
      const evidence = item.source_manifest.evidence ?? [];
      const proposal = item.selection_proposal?.candidate;
      const advisory = item.llm_analysis;
      return <article className={item.outcome === "RECOMMENDED" ? "candidate-card candidate-eligible" : "candidate-card candidate-excluded"} key={item.run_id}><header><div><span>{item.outcome}</span><h4>{label}</h4></div><strong>{advisory.state === "COMPLETED" ? "analysis completed" : "analysis unavailable"}</strong></header>{item.block_reasons.length ? <p><strong>Blocked:</strong> {item.block_reasons.map(readable).join(" · ")}</p> : null}<section aria-label={`${label} source evidence`}><h5>Source evidence</h5><EvidenceList evidence={evidence} /></section>{item.fallback_path.length ? <details><summary>Fallback trail</summary><ol>{item.fallback_path.map((step, index) => <li key={`${step.role}-${index}`}>{step.role}: {step.accepted ? "selected" : step.reason_codes.map(readable).join(" · ")}</li>)}</ol></details> : null}<section aria-label={`${label} candidates`}><h5>Candidate ranking</h5>{item.candidates.length ? <div className="candidate-list">{item.candidates.map((candidate) => <CandidateDetails candidate={{ ...candidate, category: item.category }} key={candidate.id} />)}</div> : <p className="workspace-notice">No candidates were assessed for this category.</p>}</section><section aria-label={`${label} advisory analysis`}><h5>Advisory analysis</h5><dl><div><dt>State</dt><dd>{advisory.state}</dd></div><div><dt>Provider and model</dt><dd>{advisory.provider ?? "Not recorded"} · {advisory.exact_model_id ?? "Not recorded"}</dd></div><div><dt>Attempts</dt><dd>{advisory.attempt_count}</dd></div><div><dt>Authority</dt><dd>Advisory only; deterministic rules remain authoritative</dd></div></dl>{advisory.analysis ? <dl>{Object.entries(advisory.analysis).map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{reportValue(value)}</dd></div>)}</dl> : <p><strong>Failure reason:</strong> {advisory.failure_reason ? readable(advisory.failure_reason) : "No advisory output was recorded."}</p>}{advisory.retry_eligible && onRetry ? <button className="secondary-button" onClick={() => onRetry(item.run_id)} type="button">Retry {label} pinned analysis</button> : null}</section><details><summary>Category policy pins and deterministic hash</summary><dl><div><dt>Policy pins</dt><dd>{reportValue(item.policy_pins)}</dd></div><div><dt>Result hash</dt><dd>{item.deterministic_result_hash ?? "Not recorded"}</dd></div></dl></details>{proposal && onReview ? <button onClick={() => onReview({ ...proposal, category: item.category })} type="button">Review {label} proposal for activation</button> : <p className="workspace-notice">No eligible proposal is available for human review.</p>}</article>;
    })}</div></section>;
  }
  return <section aria-labelledby="research-report"><h3 id="research-report">Market research report</h3><p>Eligibility evidence is evaluated before any score or rank. Method: <strong>{methodologyVersion ?? "Not run"}</strong>.</p>{candidates.length ? <div className="candidate-list">{candidates.map((candidate) => <article className={candidate.eligible ? "candidate-card candidate-eligible" : "candidate-card candidate-excluded"} key={candidate.id}><header><div><span>{candidate.rank ? `Rank ${candidate.rank}` : "Excluded"}</span><h4>{candidate.symbol}</h4></div>{candidate.eligible ? <strong>Score {candidate.score}</strong> : null}</header>{candidate.eligible ? <dl><div><dt>Volatility</dt><dd>{candidate.components.volatility}</dd></div><div><dt>Liquidity</dt><dd>{candidate.components.liquidity}</dd></div><div><dt>Cost quality</dt><dd>{candidate.components.cost_quality}</dd></div><div><dt>Confidence</dt><dd>{candidate.confidence}</dd></div></dl> : <p><strong>Failed gates:</strong> {candidate.exclusions.map(readable).join(" · ")}</p>}{candidate.eligible && onReview ? <button className="secondary-button" onClick={() => onReview(candidate)} type="button">Review for activation</button> : null}</article>)}</div> : <p className="workspace-notice">No candidates were assessed for this category.</p>}</section>;
}
