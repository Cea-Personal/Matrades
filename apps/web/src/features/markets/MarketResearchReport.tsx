import type { CoordinatedMarketResearchReport } from "@/lib/api/generated";

export type MarketCandidate = {
  id: string;
  symbol: string;
  display_name: string;
  eligible: boolean;
  score: string | null;
  rank: number | null;
  confidence: string;
  exclusions: string[];
  components: Record<string, string>;
  category?: "COMMODITY" | "FOREX" | "CRYPTO";
};

export function MarketResearchReport({ candidates = [], methodologyVersion, coordinated, onRetry, onReview }: { candidates?: MarketCandidate[]; methodologyVersion?: string; coordinated?: CoordinatedMarketResearchReport; onRetry?: (runId: string) => void; onReview?: (candidate: MarketCandidate) => void }) {
  if (coordinated) {
    const retryRun = coordinated.categories.find((item) => item.llm_analysis.state !== "COMPLETED")?.run_id;
    const proposed = coordinated.categories.flatMap((item) => (item.candidates ?? []).map((candidate) => ({ ...candidate, category: item.category } as unknown as MarketCandidate))).find((candidate) => candidate.eligible);
    return <section aria-label="Coordinated market research"><header><p className="section-kicker">Immutable coordinated run</p><h3>Three-category research report</h3><p><strong>Ranking is not activation.</strong> The active market is preserved until a separate human confirmation.</p></header><dl className="evidence-metrics"><div><dt>Run state</dt><dd>{coordinated.state}</dd></div><div><dt>Method</dt><dd>{coordinated.methodology_version}</dd></div><div><dt>Pinned model</dt><dd>{coordinated.exact_model_id ?? "No advisory model"}</dd></div><div><dt>Catalogue</dt><dd>{coordinated.source_catalogue_revision}</dd></div></dl><div className="candidate-list">{coordinated.categories.map((item) => { const label = item.category === "CRYPTO" ? "Cryptocurrency" : item.category === "COMMODITY" ? "Commodity" : "Forex"; const evidence = item.source_manifest.evidence ?? []; return <article className={item.outcome === "BLOCKED" ? "candidate-card candidate-excluded" : "candidate-card candidate-eligible"} key={item.run_id}><header><div><span>{item.outcome}</span><h4>{label}</h4></div><strong>{item.llm_analysis.state === "COMPLETED" ? "analysis completed" : "analysis unavailable"}</strong></header>{item.block_reasons.length ? <p><strong>Blocked:</strong> {item.block_reasons.join(" · ")}</p> : null}<dl>{evidence.map((source) => <div key={`${source.provider}-${source.capability}`}><dt>{source.provider} · {source.capability}</dt><dd>{source.semantics} · {source.freshness}{source.venue ? ` · ${source.venue}` : ""}</dd></div>)}</dl>{item.fallback_path.length ? <details><summary>Fallback trail</summary><ol>{item.fallback_path.map((step) => <li key={step.role}>{step.role}: {step.accepted ? "selected" : step.reason_codes.join(" · ")}</li>)}</ol></details> : null}</article>; })}</div>{retryRun && onRetry ? <button className="secondary-button" onClick={() => onRetry(retryRun)} type="button">Retry pinned analysis</button> : null}{proposed && onReview ? <button onClick={() => onReview(proposed)} type="button">Review for activation</button> : null}</section>;
  }
  return <section aria-labelledby="research-report"><h3 id="research-report">Market research report</h3><p>Eligibility evidence is evaluated before any score or rank. Method: <strong>{methodologyVersion ?? "Not run"}</strong>.</p>{candidates.length ? <div className="candidate-list">{candidates.map((candidate) => <article className={candidate.eligible ? "candidate-card candidate-eligible" : "candidate-card candidate-excluded"} key={candidate.id}><header><div><span>{candidate.rank ? `Rank ${candidate.rank}` : "Excluded"}</span><h4>{candidate.symbol}</h4></div>{candidate.eligible ? <strong>Score {candidate.score}</strong> : null}</header>{candidate.eligible ? <dl><div><dt>Volatility</dt><dd>{candidate.components.volatility}</dd></div><div><dt>Liquidity</dt><dd>{candidate.components.liquidity}</dd></div><div><dt>Cost quality</dt><dd>{candidate.components.cost_quality}</dd></div><div><dt>Confidence</dt><dd>{candidate.confidence}</dd></div></dl> : <p><strong>Failed gates:</strong> {candidate.exclusions.map((reason) => reason.replaceAll("_", " ").toLowerCase()).join(" · ")}</p>}{candidate.eligible && onReview ? <button className="secondary-button" onClick={() => onReview(candidate)} type="button">Review for activation</button> : null}</article>)}</div> : <p className="workspace-notice">No candidates were assessed for this category.</p>}</section>;
}
