import { useState, type FormEvent } from "react";

type ActiveMarket = { instrument_id: string; symbol: string; category: string };
export type LiteLlmModelOption = { alias: string; provider_model: string };

export type AiStrategyResearchReport = {
  job: { id: string; state: string; progress: { message?: string }; error_code?: string };
  result?: {
    state?: string;
    reason?: string;
    manual_strategy_description?: string | null;
    selection_policy?: string;
    outcomes?: Array<{
      symbol?: string;
      category?: string;
      state: string;
      reason?: string;
      lifecycle?: string;
      selection?: {
        strategy_family?: string;
        direction?: string;
        primary_timeframe?: string;
        confidence?: number;
        rationale?: string;
        cautions?: string[];
      };
      strategy_blueprint?: {
        title?: string;
        family?: string;
        direction?: string;
        timeframe?: string;
        market_regime?: string;
        entry_qualification?: string;
        liquidity_filter?: string;
        stop_loss?: string;
        take_profit?: string;
        invalidation?: string;
        expiry?: string;
        risk_per_trade?: string;
      };
    }>;
  };
};

export function AiStrategyResearch({
  activeMarkets,
  busy,
  modelAliases,
  fullModelAlias,
  manualModelAlias,
  report,
  onResearch,
  onDevelopIdea,
  onFullModelAliasChange,
  onManualModelAliasChange
}: {
  activeMarkets: ActiveMarket[];
  busy: boolean;
  modelAliases: LiteLlmModelOption[];
  fullModelAlias: string;
  manualModelAlias: string;
  report?: AiStrategyResearchReport;
  onResearch: () => Promise<void>;
  onDevelopIdea: (instrumentId: string, description: string) => Promise<void>;
  onFullModelAliasChange: (value: string) => void;
  onManualModelAliasChange: (value: string) => void;
}) {
  const required = ["FOREX", "COMMODITY", "CRYPTO"];
  const missing = required.filter((category) => !activeMarkets.some((market) => market.category === category));
  const running = report?.job.state === "QUEUED" || report?.job.state === "RUNNING";
  const [ideaInstrumentId, setIdeaInstrumentId] = useState(activeMarkets[0]?.instrument_id ?? "");
  const [ideaDescription, setIdeaDescription] = useState("");
  const submitIdea = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!ideaInstrumentId || ideaDescription.trim().length < 16) return;
    await onDevelopIdea(ideaInstrumentId, ideaDescription.trim());
  };
  return <section aria-labelledby="ai-strategy-research">
    <p className="section-kicker">AI-designed, deterministic drafts</p>
    <h3 id="ai-strategy-research">Research a strategy for each active pair</h3>
    <p>TraderX asks the selected model alias to select the best strategy family for each active Forex, Commodity, and Crypto market. It then compiles that selection into an exact, reviewable strategy blueprint—not a trade recommendation.</p>
    <div className="active-market-list">
      {required.map((category) => {
        const market = activeMarkets.find((item) => item.category === category);
        return <span key={category}><strong>{category}</strong> · {market?.symbol ?? "No active market"}</span>;
      })}
    </div>
    <label htmlFor="full-ai-strategy-model-alias">Full AI strategy-research model alias<select id="full-ai-strategy-model-alias" onChange={(event) => onFullModelAliasChange(event.target.value)} value={fullModelAlias}>
      {modelAliases.length ? modelAliases.map((model) => <option key={model.alias} value={model.alias}>{model.alias} · {model.provider_model}</option>) : <option value="">No configured LiteLLM aliases</option>}
    </select></label>
    <p className="field-hint">This alias is pinned to the individual strategy-research job. Select a different alias before either research path if desired.</p>
    {missing.length ? <p className="workspace-notice">Activate one eligible market for: {missing.join(", ")}, then return here.</p> : null}
    {!modelAliases.length ? <p className="workspace-notice">Add and qualify at least one LiteLLM model alias in Integrations before strategy research.</p> : null}
    <button disabled={busy || running || missing.length > 0 || !fullModelAlias} onClick={() => void onResearch()} type="button">
      {running ? report?.job.progress.message ?? "Researching…" : busy ? "Starting…" : "Research one strategy per active pair"}
    </button>
    <p className="workspace-notice">The result is an immutable <strong>DRAFT</strong> with defined entry qualification, filters, risk, exit, expiry, and invalidation. Backtesting, validation, paper trading, and your approvals remain required.</p>
    <form className="setup-form" onSubmit={(event) => void submitIdea(event)}>
      <p className="section-kicker">Develop your strategy idea</p>
      <h4>Describe a strategy; let AI make the draft</h4>
      <p>For example: “Trade trend continuation after a London-session pullback, but avoid high-volatility reversals.” TraderX will test it against the chosen active market and constrain it to approved deterministic rules.</p>
      <label htmlFor="strategy-idea-market">Active market<select id="strategy-idea-market" onChange={(event) => setIdeaInstrumentId(event.target.value)} value={ideaInstrumentId}>
        {activeMarkets.map((market) => <option key={market.instrument_id} value={market.instrument_id}>{market.category} · {market.symbol}</option>)}
      </select></label>
      <label htmlFor="manual-ai-strategy-model-alias">Manual idea model alias<select id="manual-ai-strategy-model-alias" onChange={(event) => onManualModelAliasChange(event.target.value)} value={manualModelAlias}>
        {modelAliases.length ? modelAliases.map((model) => <option key={model.alias} value={model.alias}>{model.alias} · {model.provider_model}</option>) : <option value="">No configured LiteLLM aliases</option>}
      </select></label>
      <p className="field-hint">This model alias is pinned only to this manual strategy-idea research job.</p>
      <label htmlFor="strategy-idea-description">Your strategy description<textarea id="strategy-idea-description" minLength={16} onChange={(event) => setIdeaDescription(event.target.value)} placeholder="Describe the market behavior, setup, timing, and conditions you want researched." required value={ideaDescription} /></label>
      <button disabled={busy || running || !manualModelAlias || !ideaInstrumentId || ideaDescription.trim().length < 16} type="submit">{busy ? "Starting…" : "Develop this strategy idea with AI"}</button>
    </form>
    {report?.result?.reason ? <p className="status-message" data-tone="error" role="alert">{report.result.reason}</p> : null}
    {report?.result?.manual_strategy_description ? <p className="workspace-notice">Developed idea: {report.result.manual_strategy_description}</p> : null}
    {report?.result?.outcomes?.length ? <div className="strategy-list" aria-label="AI strategy research results">
      {report.result.outcomes.map((outcome, index) => <article key={`${outcome.symbol ?? "result"}-${index}`}>
        <strong>{outcome.category ? `${outcome.category} · ` : ""}{outcome.symbol ?? "Active market"}</strong>
        <p>{outcome.state}{outcome.lifecycle ? ` · ${outcome.lifecycle}` : ""}{outcome.reason ? ` · ${outcome.reason}` : ""}</p>
        {outcome.selection ? <>
          {outcome.strategy_blueprint ? <section aria-label={`${outcome.symbol ?? "Strategy"} blueprint`}>
            <h4>{outcome.strategy_blueprint.title ?? "Draft strategy blueprint"}</h4>
            <dl className="evidence-metrics">
              <div><dt>Regime</dt><dd>{outcome.strategy_blueprint.market_regime}</dd></div>
              <div><dt>Entry qualification</dt><dd>{outcome.strategy_blueprint.entry_qualification}</dd></div>
              <div><dt>Liquidity filter</dt><dd>{outcome.strategy_blueprint.liquidity_filter}</dd></div>
              <div><dt>Stop loss</dt><dd>{outcome.strategy_blueprint.stop_loss}</dd></div>
              <div><dt>Take profit</dt><dd>{outcome.strategy_blueprint.take_profit}</dd></div>
              <div><dt>Invalidation</dt><dd>{outcome.strategy_blueprint.invalidation}</dd></div>
              <div><dt>Expiry</dt><dd>{outcome.strategy_blueprint.expiry}</dd></div>
              <div><dt>Risk per trade</dt><dd>{outcome.strategy_blueprint.risk_per_trade}</dd></div>
            </dl>
          </section> : null}
          <p><strong>Why this strategy fits now:</strong> {outcome.selection.rationale}</p>
          {outcome.selection.cautions?.length ? <small>Cautions: {outcome.selection.cautions.join(" · ")}</small> : null}
        </> : null}
      </article>)}
    </div> : null}
  </section>;
}
