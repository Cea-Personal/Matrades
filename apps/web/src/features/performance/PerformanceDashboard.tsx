"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// Performance attribution keeps live, paper, backtest, and validation evidence separate.

type Performance = { dimension: string; evidence_class: string; groups: Record<string, { trades: number; pnl: string; expectancy: string; r: string; win_rate: string; gross_profit: string; gross_loss: string; profit_factor: string; max_drawdown: string }> };

export function PerformanceDashboard() {
  const [dimension, setDimension] = useState("strategy_version_id");
  const [evidenceClass, setEvidenceClass] = useState("LIVE");
  const report = useQuery<Performance>({ queryKey: ["operations", "performance", dimension, evidenceClass], queryFn: () => api(`/operations/performance?dimension=${dimension}&evidence_class=${evidenceClass}`) });
  return <section><h2>Performance analytics</h2><p className="muted">Evidence classes are never mixed. LIVE metrics use confirmed broker outcomes; simulations are labeled separately.</p><div className="actions"><label>Dimension<select aria-label="Dimension" value={dimension} onChange={event => setDimension(event.target.value)}><option value="strategy_version_id">Strategy version</option><option value="regime">Regime</option><option value="account_id">Account</option><option value="instrument">Instrument</option><option value="session">Session</option></select></label><label>Evidence<select aria-label="Evidence class" value={evidenceClass} onChange={event => setEvidenceClass(event.target.value)}><option>LIVE</option><option>PAPER</option><option>BACKTEST</option></select></label></div>{report.isPending ? <p>Calculating…</p> : Object.keys(report.data?.groups ?? {}).length ? <div className="table-wrap card"><table><thead><tr><th>{dimension.replaceAll("_", " ")}</th><th>Trades</th><th>Net P&amp;L</th><th>Expectancy / edge</th><th>Win rate</th><th>Profit factor</th><th>Max DD</th></tr></thead><tbody>{Object.entries(report.data?.groups ?? {}).map(([name, value]) => <tr key={name}><td>{name}</td><td>{value.trades}</td><td>{value.pnl}</td><td>{value.expectancy} / {value.r}</td><td>{Math.round(Number(value.win_rate) * 100)}%</td><td>{value.profit_factor}</td><td>{value.max_drawdown}</td></tr>)}</tbody></table></div> : <p className="empty card">No {evidenceClass.toLowerCase()} performance observations yet.</p>}</section>;
}
