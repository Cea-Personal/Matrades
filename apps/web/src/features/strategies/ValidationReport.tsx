export function ValidationReport({ state = "PENDING" }: { state?: string }) {
  return <section aria-labelledby="validation-report"><h2 id="validation-report">Validation evidence</h2><p>Status: {state}. Out-of-sample, robustness, tail-risk, and portfolio evidence are all required.</p></section>;
}
