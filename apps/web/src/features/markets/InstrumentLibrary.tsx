type Instrument = { symbol: string; category: string; dataStatus: string };

export function InstrumentLibrary({ instruments = [] }: { instruments?: Instrument[] }) {
  return <section aria-labelledby="instrument-library"><h2 id="instrument-library">Instrument Library</h2><p>Research data is never a live-market activation.</p><ul>{instruments.map((item) => <li key={item.symbol}>{item.symbol} · {item.category} · {item.dataStatus}</li>)}</ul></section>;
}
