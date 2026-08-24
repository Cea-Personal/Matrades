"use client";

export function ValidationResults({ gates, promotable, onPromote }: { gates: Record<string, boolean>; promotable: boolean; onPromote: () => void }) {
  return <article className="card"><h2>Validation evidence</h2>{Object.keys(gates).length ? <table><tbody>{Object.entries(gates).map(([stage, passed]) => <tr key={stage}><td>{stage.replaceAll("_", " ")}</td><td className={passed ? "good" : "bad"}>{passed ? "Passed" : "Failed"}</td></tr>)}</tbody></table> : <p className="empty">No evaluator evidence.</p>}<button className="btn primary" disabled={!promotable} onClick={onPromote}>Promote passing version</button></article>;
}
