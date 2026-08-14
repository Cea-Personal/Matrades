export type ActiveMarket = { id: string; category: string; symbol: string; state: string; version: number; etag: string; approval_reason?: string | null };

export function ActiveMarkets({ assignments = [], onDeactivate }: { assignments?: ActiveMarket[]; onDeactivate?: (assignment: ActiveMarket) => void }) {
  const slots = ["COMMODITY", "FOREX", "CRYPTO"];
  return <section aria-labelledby="active-markets"><h3 id="active-markets">Human-approved active markets</h3><p>Exactly one slot per category. A new ranking never replaces a selection silently.</p><div className="active-market-grid">{slots.map((category) => { const assignment = assignments.find((item) => item.category === category); return <article key={category}><span>{category === "CRYPTO" ? "Cryptocurrency" : category.toLowerCase()}</span><strong>{assignment?.symbol ?? "Inactive"}</strong><small>{assignment ? `Approved · version ${assignment.version}` : "Awaiting an eligible human-approved selection"}</small>{assignment && onDeactivate ? <button className="secondary-button" onClick={() => onDeactivate(assignment)} type="button">Review deactivation</button> : null}</article>; })}</div></section>;
}
