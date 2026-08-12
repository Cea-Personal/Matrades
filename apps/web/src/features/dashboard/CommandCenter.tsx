export function CommandCenter({ state = "LOCKDOWN", capacity = 0 }: { state?: string; capacity?: number }) {
  return <section aria-label="Command Center"><h1>Command Center</h1><dl><dt>Risk state</dt><dd>{state}</dd><dt>Position capacity</dt><dd>{capacity} / 2</dd></dl><p>New recommendations remain blocked until account data is verified.</p></section>;
}
