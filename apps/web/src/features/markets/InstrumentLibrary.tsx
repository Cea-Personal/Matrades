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
  source_coverage?: Array<{ provider: string; provider_symbol: string; venue?: string | null; mapping_revision: string; mapping_status: string; entitlement_status: string; semantics: string }>;
  capability_status?: Record<string, string>;
};

export type SpecialistIntegration = {
  id: string;
  provider: string;
  state: string;
  entitlement_status: string;
};

type MappingInput = {
  integrationId: string;
  providerSymbol: string;
  venue: string;
  contractVariant?: string;
  reason: string;
};

const mappingProfile: Record<string, { provider: string; venues: string[]; contractVariant: boolean }> = {
  COMMODITY: { provider: "CME_GROUP", venues: ["COMEX", "NYMEX", "CME", "CBOT"], contractVariant: true },
  FOREX: { provider: "CBOE_FX_SPOT", venues: ["CBOE_FX_SPOT"], contractVariant: false },
  CRYPTO: { provider: "COINBASE_EXCHANGE", venues: ["COINBASE_EXCHANGE"], contractVariant: false }
};

export function InstrumentLibrary({ instruments = [], integrations = [], busy = false, onRunResearch, onApproveMapping }: { instruments?: MarketInstrument[]; integrations?: SpecialistIntegration[]; busy?: boolean; onRunResearch?: () => void; onApproveMapping?: (instrument: MarketInstrument, mapping: MappingInput) => void }) {
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
              <span role="cell"><strong>{item.status}</strong><details><summary>Evidence history</summary><small>Version {item.version ?? 1}<br />Last assessed {item.quality_observed_at ? new Date(item.quality_observed_at).toLocaleString() : "not yet"}</small>{item.source_coverage?.map((source) => <p key={`${source.provider}-${source.provider_symbol}`}><strong>{source.provider}</strong> · {source.provider_symbol}{source.venue ? ` · ${source.venue}` : ""}<br />{source.semantics} · mapping {source.mapping_revision} · entitlement {source.entitlement_status}</p>)}{item.capability_status ? <p>{Object.entries(item.capability_status).map(([name, state]) => `${name}: ${state}`).join(" · ")}</p> : null}</details>{onApproveMapping && mappingProfile[item.category] && !item.source_coverage?.some((source) => source.provider === mappingProfile[item.category].provider && source.mapping_status === "APPROVED") ? <details><summary>Approve specialist symbol mapping</summary><MappingForm busy={busy} instrument={item} integrations={integrations} onApprove={onApproveMapping} /></details> : null}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="workspace-notice"><p>No instruments match these filters. Inactive instruments remain available for research after broker data is refreshed.</p>{onRunResearch ? <button className="secondary-button" disabled={busy} onClick={onRunResearch} type="button">Research this category</button> : null}</div>
      )}
    </section>
  );
}

function MappingForm({ instrument, integrations, busy, onApprove }: { instrument: MarketInstrument; integrations: SpecialistIntegration[]; busy: boolean; onApprove: (instrument: MarketInstrument, mapping: MappingInput) => void }) {
  const profile = mappingProfile[instrument.category];
  const eligible = integrations.filter((item) => item.provider === profile.provider && item.state === "HEALTHY" && item.entitlement_status !== "UNVERIFIED" && item.entitlement_status !== "DECLARED");
  return <form className="integration-form" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); onApprove(instrument, { integrationId: String(form.get("mapping-integration")), providerSymbol: String(form.get("mapping-symbol")), venue: String(form.get("mapping-venue")), contractVariant: profile.contractVariant ? String(form.get("mapping-contract")) : undefined, reason: String(form.get("mapping-reason")) }); }}><p>Map this exact MT5 contract to a reviewed venue symbol. The mapping does not activate a market.</p><label>Qualified specialist<select name="mapping-integration" required><option value="">Select provider</option>{eligible.map((item) => <option key={item.id} value={item.id}>{item.provider}</option>)}</select></label><label>Provider symbol<input name="mapping-symbol" placeholder={instrument.category === "CRYPTO" ? "BTC-USD" : instrument.category === "FOREX" ? "EUR/USD" : "GC"} required /></label><label>Venue<select name="mapping-venue" required>{profile.venues.map((venue) => <option key={venue}>{venue}</option>)}</select></label>{profile.contractVariant ? <label>Contract variant<input name="mapping-contract" placeholder="e.g. front-month gold futures" required /></label> : null}<label>Approval reason<textarea minLength={8} name="mapping-reason" required /></label><button disabled={busy || eligible.length === 0} type="submit">Approve mapping</button>{eligible.length === 0 ? <p role="status">Qualify and verify the category specialist in Integrations first.</p> : null}</form>;
}
