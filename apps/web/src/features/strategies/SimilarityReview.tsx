"use client";

type Similarity = { classification: string; structural: number; exact: boolean };

export function SimilarityReview({ result, onAction }: { result: Similarity | null; onAction: (action: "REVIEW_EXISTING" | "BRANCH_VERSION" | "KEEP_DISTINCT") => void }) {
  if (!result) return <article className="card empty">Similarity evidence appears after comparing canonical specifications.</article>;
  return <article className="card"><h2>Similarity review</h2><strong>{Math.round(result.structural * 100)}% structural match · {result.classification}</strong><p className="muted">Review parameters, provenance, and behavior. Assistant changes remain proposals: Accept, Edit, or Reject before persistence.</p><div className="actions"><button className="btn" onClick={() => onAction("REVIEW_EXISTING")}>Reuse</button><button className="btn" onClick={() => onAction("BRANCH_VERSION")}>Create variant</button><button className="btn" onClick={() => onAction("KEEP_DISTINCT")}>Keep distinct</button></div></article>;
}
