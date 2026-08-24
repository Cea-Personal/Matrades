"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// Performance attribution uses actual reconciled broker outcomes.

type Performance = { dimension: string; groups: Record<string, { trade_count: number; net_pnl: string; expectancy: string; win_rate: number }> };

export function PerformanceDashboard() {
  const [dimension, setDimension] = useState("strategy_version");
  const report = useQuery<Performance>({ queryKey: ["operations", "performance", dimension], queryFn: () => api(`/operations/performance?dimension=${dimension}`) });
  return <section><h2>Actual broker performance</h2><select aria-label="Dimension" value={dimension} onChange={event => setDimension(event.target.value)}><option value="strategy_version">Strategy version</option><option value="regime">Regime</option><option value="account_id">Account</option><option value="agent_configuration">Agent configuration</option></select>{report.isPending ? <p>Calculating…</p> : Object.keys(report.data?.groups ?? {}).length ? <div className="table-wrap card"><table><thead><tr><th>{dimension.replaceAll("_", " ")}</th><th>Trades</th><th>Net P&amp;L</th><th>Expectancy</th><th>Win rate</th></tr></thead><tbody>{Object.entries(report.data?.groups ?? {}).map(([name, value]) => <tr key={name}><td>{name}</td><td>{value.trade_count}</td><td>{value.net_pnl}</td><td>{value.expectancy}</td><td>{Math.round(value.win_rate * 100)}%</td></tr>)}</tbody></table></div> : <p className="empty card">No reconciled broker performance yet.</p>}</section>;
}
