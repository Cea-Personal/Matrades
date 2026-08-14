"use client";

import { useMemo, useState } from "react";

export type MarketInstrument = {
  id: string;
  symbol: string;
  display_name: string;
  category: string;
  status: string;
  data_status: string;
  version?: number;
  quality_observed_at?: string | null;
  quality_reason_codes?: string[];
};

export function InstrumentLibrary({ instruments = [], busy = false, onRunResearch }: { instruments?: MarketInstrument[]; busy?: boolean; onRunResearch?: () => void }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [dataStatus, setDataStatus] = useState("ALL");
  const filtered = useMemo(() => instruments.filter((item) => {
    const matchesQuery = `${item.symbol} ${item.display_name}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (status === "ALL" || item.status === status) && (dataStatus === "ALL" || item.data_status === dataStatus);
  }), [dataStatus, instruments, query, status]);
  const verified = instruments.filter((item) => item.data_status === "VERIFIED").length;

  return (
    <section aria-labelledby="instrument-library">
      <h3 id="instrument-library">Instrument Library</h3>
      <p>Broker-supported instruments and their research-data readiness. A library record is never a live-market activation.</p>
      <div className="library-summary" aria-label="Instrument counts">
        <strong>{instruments.length} broker instruments</strong><span>{verified} data verified</span><span>{filtered.length} shown</span>
      </div>
      <div className="library-filters">
        <label htmlFor="instrument-search">Find instrument<input id="instrument-search" onChange={(event) => setQuery(event.target.value)} placeholder="Symbol or name" type="search" value={query} /></label>
        <label htmlFor="instrument-status">Lifecycle<select id="instrument-status" onChange={(event) => setStatus(event.target.value)} value={status}><option value="ALL">All states</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option><option value="QUARANTINED">Quarantined</option></select></label>
        <label htmlFor="instrument-data-status">Data<select id="instrument-data-status" onChange={(event) => setDataStatus(event.target.value)} value={dataStatus}><option value="ALL">All data</option><option value="VERIFIED">Verified</option><option value="INSUFFICIENT">Insufficient</option><option value="QUARANTINED">Quarantined</option></select></label>
      </div>
      {filtered.length ? (
        <div className="evidence-table" role="table" aria-label="Instrument Library">
          <div className="evidence-row evidence-header" role="row"><span role="columnheader">Instrument</span><span role="columnheader">Category</span><span role="columnheader">Data</span><span role="columnheader">State and history</span></div>
          {filtered.map((item) => (
            <div className="evidence-row" role="row" key={item.id}>
              <span role="cell"><strong>{item.symbol}</strong><small>{item.display_name}</small></span>
              <span role="cell">{item.category}</span>
              <span role="cell"><strong>{item.data_status}</strong><small>{item.quality_reason_codes?.length ? item.quality_reason_codes.join(" · ") : "No failed quality gates"}</small></span>
              <span role="cell"><strong>{item.status}</strong><details><summary>Evidence history</summary><small>Version {item.version ?? 1}<br />Last assessed {item.quality_observed_at ? new Date(item.quality_observed_at).toLocaleString() : "not yet"}</small></details></span>
            </div>
          ))}
        </div>
      ) : (
        <div className="workspace-notice"><p>No instruments match these filters. Inactive instruments remain available for research after broker data is refreshed.</p>{onRunResearch ? <button className="secondary-button" disabled={busy} onClick={onRunResearch} type="button">Research this category</button> : null}</div>
      )}
    </section>
  );
}
