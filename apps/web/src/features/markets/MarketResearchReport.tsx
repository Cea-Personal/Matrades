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
};

export function MarketResearchReport({ candidates = [], methodologyVersion, onReview }: { candidates?: MarketCandidate[]; methodologyVersion?: string; onReview?: (candidate: MarketCandidate) => void }) {
  return <section aria-labelledby="research-report"><h3 id="research-report">Market research report</h3><p>Eligibility evidence is evaluated before any score or rank. Method: <strong>{methodologyVersion ?? "Not run"}</strong>.</p>{candidates.length ? <div className="candidate-list">{candidates.map((candidate) => <article className={candidate.eligible ? "candidate-card candidate-eligible" : "candidate-card candidate-excluded"} key={candidate.id}><header><div><span>{candidate.rank ? `Rank ${candidate.rank}` : "Excluded"}</span><h4>{candidate.symbol}</h4></div>{candidate.eligible ? <strong>Score {candidate.score}</strong> : null}</header>{candidate.eligible ? <dl><div><dt>Volatility</dt><dd>{candidate.components.volatility}</dd></div><div><dt>Liquidity</dt><dd>{candidate.components.liquidity}</dd></div><div><dt>Cost quality</dt><dd>{candidate.components.cost_quality}</dd></div><div><dt>Confidence</dt><dd>{candidate.confidence}</dd></div></dl> : <p><strong>Failed gates:</strong> {candidate.exclusions.map((reason) => reason.replaceAll("_", " ").toLowerCase()).join(" · ")}</p>}{candidate.eligible && onReview ? <button className="secondary-button" onClick={() => onReview(candidate)} type="button">Review for activation</button> : null}</article>)}</div> : <p className="workspace-notice">No candidates were assessed for this category.</p>}</section>;
}
