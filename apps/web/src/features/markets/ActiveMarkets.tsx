type Assignment = { category: string; symbol: string; version: number };

export function ActiveMarkets({ assignments = [] }: { assignments?: Assignment[] }) {
  return <section aria-labelledby="active-markets"><h2 id="active-markets">Human-approved active markets</h2><p>One Commodity, Forex, and Cryptocurrency market only. A ranking never replaces a selection silently.</p><ul>{assignments.map((item) => <li key={item.category}>{item.category}: {item.symbol} (version {item.version})</li>)}</ul></section>;
}
