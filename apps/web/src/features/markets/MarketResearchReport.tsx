type Candidate = { symbol: string; eligible: boolean; score?: string; exclusions?: string[] };

export function MarketResearchReport({ candidates = [] }: { candidates?: Candidate[] }) {
  return <section aria-labelledby="research-report"><h2 id="research-report">Market research report</h2><p>Eligibility evidence is evaluated before any score or rank.</p><ul>{candidates.map((candidate) => <li key={candidate.symbol}>{candidate.symbol}: {candidate.eligible ? `eligible · ${candidate.score ?? "unranked"}` : `excluded · ${(candidate.exclusions ?? []).join(", ")}`}</li>)}</ul></section>;
}
