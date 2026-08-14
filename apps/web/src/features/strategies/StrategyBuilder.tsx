"use client";

import { FormEvent } from "react";

type ActiveMarket = { instrument_id: string; symbol: string; category: string };

export type StrategyDraft = {
  name: string;
  instrument_id: string;
  change_summary: string;
  definition: {
    regime: string;
    direction: string;
    timeframes: string[];
    conditions: Array<Record<string, string>>;
    filters: Array<Record<string, string>>;
    stop: Record<string, string>;
    target: Record<string, string>;
    invalidation: Record<string, string>;
    expiration: Record<string, string | number>;
    risk_fraction: string;
  };
};

export function StrategyBuilder({ activeMarkets, busy, creatingVersion, onSave }: { activeMarkets: ActiveMarket[]; busy: boolean; creatingVersion: boolean; onSave: (draft: StrategyDraft) => Promise<void> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const draft: StrategyDraft = {
      name: String(form.get("strategy-name")),
      instrument_id: String(form.get("strategy-instrument")),
      change_summary: String(form.get("change-summary")),
      definition: {
        regime: String(form.get("strategy-regime")),
        direction: String(form.get("strategy-direction")),
        timeframes: [String(form.get("strategy-timeframe"))],
        conditions: [{ field: String(form.get("entry-field")), operator: String(form.get("entry-operator")), value: String(form.get("entry-value")) }],
        filters: [{ field: "spread_bps", operator: "<", value: String(form.get("maximum-spread")) }],
        stop: { type: "PERCENT", value: String(form.get("stop-distance")) },
        target: { type: "RR", value: String(form.get("target-rr")) },
        invalidation: { type: String(form.get("invalidation")) },
        expiration: { type: "BARS", value: Number(form.get("expiration-bars")) },
        risk_fraction: String(form.get("risk-fraction"))
      }
    };
    await onSave(draft);
  }

  return <section aria-labelledby="strategy-builder"><p className="section-kicker">No-code definition</p><h3 id="strategy-builder">{creatingVersion ? "Create a new immutable version" : "Define a deterministic strategy"}</h3><p>Every material edit creates a new version. Rules are data, never executable user code.</p>{activeMarkets.length ? <form className="setup-form" onSubmit={submit}><label htmlFor="strategy-name">Strategy name<input disabled={creatingVersion} id="strategy-name" name="strategy-name" defaultValue={creatingVersion ? "Existing strategy" : ""} required /></label><label htmlFor="strategy-instrument">Active instrument<select disabled={creatingVersion} id="strategy-instrument" name="strategy-instrument" required>{activeMarkets.map((market) => <option key={market.instrument_id} value={market.instrument_id}>{market.symbol} · {market.category}</option>)}</select></label><div className="form-row"><label htmlFor="strategy-regime">Market regime<select id="strategy-regime" name="strategy-regime"><option value="TREND">Trend</option><option value="RANGE">Range</option><option value="BREAKOUT">Breakout</option></select></label><label htmlFor="strategy-direction">Direction<select id="strategy-direction" name="strategy-direction"><option value="BOTH">Long and short</option><option value="LONG">Long only</option><option value="SHORT">Short only</option></select></label></div><div className="form-row"><label htmlFor="strategy-timeframe">Decision timeframe<select id="strategy-timeframe" name="strategy-timeframe"><option value="H1">H1</option><option value="H4">H4</option><option value="D1">D1</option></select></label><label htmlFor="entry-field">Entry field<select id="entry-field" name="entry-field"><option value="close">Close price</option><option value="momentum">Momentum</option><option value="volatility">Volatility</option></select></label></div><div className="form-row"><label htmlFor="entry-operator">Entry comparison<select id="entry-operator" name="entry-operator"><option value=">">Greater than</option><option value="<">Less than</option><option value="==">Equals</option></select></label><label htmlFor="entry-value">Entry value<input id="entry-value" name="entry-value" required /></label></div><div className="form-row"><label htmlFor="stop-distance">Stop distance (fraction)<input defaultValue="0.005" id="stop-distance" max="0.2" min="0.0001" name="stop-distance" required step="0.0001" type="number" /></label><label htmlFor="target-rr">Target reward-to-risk<input defaultValue="2" id="target-rr" min="1" name="target-rr" required step="0.1" type="number" /></label></div><div className="form-row"><label htmlFor="maximum-spread">Maximum spread (bps)<input defaultValue="10" id="maximum-spread" min="0" name="maximum-spread" required type="number" /></label><label htmlFor="risk-fraction">Risk fraction<input defaultValue="0.005" id="risk-fraction" max="0.02" min="0.0001" name="risk-fraction" required step="0.0001" type="number" /></label></div><div className="form-row"><label htmlFor="invalidation">Invalidation<select id="invalidation" name="invalidation"><option value="CLOSE_BELOW_ENTRY">Close crosses entry</option><option value="REGIME_CHANGE">Regime changes</option><option value="STRUCTURE_BREAK">Structure breaks</option></select></label><label htmlFor="expiration-bars">Expiry after bars<input defaultValue="4" id="expiration-bars" min="1" name="expiration-bars" required type="number" /></label></div><label htmlFor="change-summary">Change summary<textarea id="change-summary" minLength={8} name="change-summary" required /></label><button disabled={busy} type="submit">{busy ? "Saving…" : creatingVersion ? "Create immutable version" : "Save immutable draft"}</button></form> : <p className="workspace-notice">Approve at least one eligible active market before creating a strategy.</p>}</section>;
}
