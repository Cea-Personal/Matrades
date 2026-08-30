"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

type ChartContext = {
  instrument?: string;
  candles?: Array<{ timestamp: string; open: number; high: number; low: number; close: number }>;
  overlays?: Array<{ kind: string; value?: number; label?: string }>;
  freshness?: string;
  mapping_status?: string;
};

export function ActiveTradeChart({ trade }: { trade: Resource }) {
  const position = (trade.broker_position as Record<string, unknown> | undefined) ?? {};
  const symbol = String(position.instrument ?? trade.instrument ?? "");
  const [timeframe, setTimeframe] = useState("1h");
  const [zoom, setZoom] = useState(40);
  const [offset, setOffset] = useState(0);
  const chart = useQuery<ChartContext>({
    queryKey: ["trade-chart", trade.id, timeframe],
    queryFn: () => api(`/trade-management/trades/${trade.id}/chart?timeframe=${timeframe}`),
    enabled: Boolean(trade.id),
    refetchInterval: 15_000,
  });
  const candles = chart.data?.candles ?? [];
  const visible = candles.slice(Math.max(0, candles.length - zoom - offset), Math.max(0, candles.length - offset));
  return (
    <article className="card">
      <div className="split-heading">
        <div><h3>{symbol || "Active trade"} chart</h3><p className="muted">Read-only candles and Trade Plan overlays. Chart interactions never create broker commands.</p></div>
        <span className="status">{chart.data?.freshness ?? "LOADING"} · {chart.data?.mapping_status ?? "UNMAPPED"}</span>
      </div>
      <div className="actions"><label>Timeframe<select value={timeframe} onChange={event => setTimeframe(event.target.value)}>{["5m", "15m", "1h", "4h", "1d"].map(value => <option key={value}>{value}</option>)}</select></label><button className="btn compact" disabled={offset + zoom >= candles.length} onClick={() => setOffset(offset + Math.max(1, Math.floor(zoom / 2)))}>Pan earlier</button><button className="btn compact" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - Math.max(1, Math.floor(zoom / 2))))}>Pan later</button><label>Zoom<input type="range" min="10" max="160" value={zoom} onChange={event => setZoom(Number(event.target.value))} /></label></div>
      {chart.isError ? <p className="notice bad">Chart data is unavailable; broker state remains authoritative.</p> : candles.length === 0 ? <p className="empty">No mapped candle stream is available yet.</p> : <div className="chart-strip" aria-label={`${symbol} read-only chart`}>{visible.map((candle, index) => <span key={`${candle.timestamp}-${index}`} title={`${candle.timestamp}: ${candle.close}`} style={{ height: `${Math.max(8, Math.min(100, Math.abs(candle.close - candle.open) * 1000))}%` }} className={candle.close >= candle.open ? "candle up" : "candle down"} />)}</div>}
      {chart.data?.overlays?.length ? <ul className="record-list compact-list">{chart.data.overlays.map((overlay, index) => <li key={`${overlay.kind}-${index}`}><strong>{overlay.kind}</strong><span>{overlay.label ?? overlay.value ?? "—"}</span></li>)}</ul> : null}
    </article>
  );
}
