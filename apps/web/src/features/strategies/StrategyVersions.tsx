export function StrategyVersions({ versions = [] }: { versions?: { version: number; state: string }[] }) {
  return <section aria-labelledby="strategy-versions"><h2 id="strategy-versions">Immutable versions</h2><ul>{versions.map((item) => <li key={item.version}>Version {item.version}: {item.state}</li>)}</ul></section>;
}
