"use client";

import { useState } from "react";

export type StrategyVersionSummary = { id: string; sequence: number; lifecycle: string; definition_hash: string; change_summary: string; immutable: boolean; definition?: Record<string, unknown>; created_at?: string; etag?: string };
export type StrategySummary = { id: string; name: string; instrument_id: string; version: number; etag: string; versions: StrategyVersionSummary[] };

export function StrategyVersions({ strategies, selectedStrategyId, selectedVersionId, onSelectStrategy, onSelectVersion }: { strategies: StrategySummary[]; selectedStrategyId?: string; selectedVersionId?: string; onSelectStrategy: (strategy: StrategySummary) => void; onSelectVersion: (version: StrategyVersionSummary) => void }) {
  const [comparisonId, setComparisonId] = useState<string>();
  const selectedStrategy = strategies.find((item) => item.id === selectedStrategyId);
  const selectedVersion = selectedStrategy?.versions.find((item) => item.id === selectedVersionId);
  const comparison = selectedStrategy?.versions.find((item) => item.id === comparisonId);
  const changedSections = (() => {
    if (!selectedVersion?.definition || !comparison?.definition) return [];
    return Array.from(new Set([...Object.keys(selectedVersion.definition), ...Object.keys(comparison.definition)])).filter((key) => JSON.stringify(selectedVersion.definition?.[key]) !== JSON.stringify(comparison.definition?.[key]));
  })();

  return (
    <section aria-labelledby="strategy-versions">
      <h3 id="strategy-versions">Immutable versions</h3>
      <p>Select the exact version whose evidence you want to inspect or extend. Historical definitions never change.</p>
      {strategies.length ? <div className="strategy-list">{strategies.map((strategy) => <article key={strategy.id}><button aria-pressed={selectedStrategyId === strategy.id} className="secondary-button" onClick={() => { onSelectStrategy(strategy); setComparisonId(undefined); }} type="button">{strategy.name}</button>{selectedStrategyId === strategy.id ? <ul>{strategy.versions.map((version) => <li key={version.id}><button aria-pressed={selectedVersionId === version.id} className="secondary-button" onClick={() => onSelectVersion(version)} type="button">Version {version.sequence} · {version.lifecycle}</button><small>{version.change_summary}</small></li>)}</ul> : null}</article>)}</div> : <p className="workspace-notice">No strategy has been created yet.</p>}
      {selectedVersion ? <div className="version-evidence"><dl className="evidence-metrics"><div><dt>Selected version</dt><dd>{selectedVersion.sequence}</dd></div><div><dt>Lifecycle</dt><dd>{selectedVersion.lifecycle}</dd></div><div><dt>Definition hash</dt><dd title={selectedVersion.definition_hash}>{selectedVersion.definition_hash.slice(0, 14)}…</dd></div></dl><p className="workspace-notice">{lifecycleGuidance(selectedVersion.lifecycle)}</p>{selectedStrategy && selectedStrategy.versions.length > 1 ? <label htmlFor="compare-version">Compare with<select id="compare-version" onChange={(event) => setComparisonId(event.target.value || undefined)} value={comparisonId ?? ""}><option value="">Choose a version</option>{selectedStrategy.versions.filter((item) => item.id !== selectedVersion.id).map((item) => <option key={item.id} value={item.id}>Version {item.sequence}</option>)}</select></label> : null}{comparison ? <p><strong>Changed sections:</strong> {changedSections.length ? changedSections.join(" · ") : "No canonical definition differences"}</p> : null}</div> : null}
    </section>
  );
}

function lifecycleGuidance(lifecycle: string): string {
  if (["LIVE", "LIVE_APPROVED"].includes(lifecycle)) return "This version has passed historical, paper, and human approval gates.";
  if (["BACKTEST_PASSED", "PAPER_READY", "PAPER_TRADING"].includes(lifecycle)) return "Historical validation passed; paper evidence and human approval are still required.";
  if (lifecycle === "FAILED") return "Validation failed. Create a new immutable draft to revise the rules.";
  return "Backtest, validation, paper evidence, and human approval prerequisites remain unmet.";
}
