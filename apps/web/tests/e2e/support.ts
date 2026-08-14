import type { Page } from "@playwright/test";

export async function mockReadyCommandCenter(page: Page, options: { seedActiveMarket?: boolean; seedPaperEvidence?: boolean; seedOpportunities?: boolean; seedMonitoring?: boolean; seedJournal?: boolean; seedOperations?: boolean } = {}) {
  const symbols: Record<string, string> = { COMMODITY: "XAUUSD", FOREX: "EURUSD", CRYPTO: "BTCUSD" };
  const activeMarkets: Array<{ id: string; instrument_id: string; symbol: string; category: string; state: string; version: number; etag: string }> = [];
  if (options.seedActiveMarket) activeMarkets.push({ id: "active-FOREX", instrument_id: "instrument-FOREX", symbol: "EURUSD", category: "FOREX", state: "ACTIVE", version: 1, etag: '"active-FOREX-1"' });
  const strategies: Array<Record<string, unknown>> = [];
  const validations: Array<Record<string, unknown>> = [];
  const paperRuns: Array<Record<string, unknown>> = [];
  const opportunities: Array<Record<string, unknown>> = [];
  const positions: Array<Record<string, unknown>> = [];
  const journalEntries: Array<Record<string, unknown>> = [];
  const jobs: Array<Record<string, unknown>> = options.seedOperations ? [{ id: "job-operations-1", type: "MARKET_RESEARCH", state: "RUNNING", progress: { stage: "SCREENING", completed_units: 3, total_units: 10 }, attempt_count: 1, available_actions: ["CANCEL", "PAUSE"], created_at: "2026-08-14T10:00:00Z" }] : [];
  const notificationPreferences: Array<Record<string, unknown>> = options.seedOperations ? [{ id: "preference-web", channel: "WEB", minimum_severity: "INFO", enabled: true }] : [];
  const notices: Array<Record<string, unknown>> = [];
  const mt5Integrations: Array<Record<string, unknown>> = options.seedOperations ? [{ id: "integration-1", version: 1, category: "BROKER", provider: "MT5_TERMINAL_BRIDGE", name: "MT5 MetaQuotes-Demo 5054425064", mt5_account_login: "5054425064", mt5_server: "MetaQuotes-Demo", status: "HEALTHY", credential_hint: "configured; verified" }] : [];
  if (options.seedPaperEvidence) {
    activeMarkets.push({ id: "active-FOREX", instrument_id: "instrument-FOREX", symbol: "EURUSD", category: "FOREX", state: "ACTIVE", version: 1, etag: '"active-FOREX-1"' });
    strategies.push({ id: "strategy-1", name: "H1 trend continuation", instrument_id: "instrument-FOREX", version: 1, etag: '"strategy-strategy-1-1"', versions: [{ id: "version-1", sequence: 1, lifecycle: "BACKTEST_PASSED", definition_hash: "strategy-definition-hash-v1", change_summary: "Validated fixture", immutable: true, etag: '"strategy-version-version-1-1"' }] });
    validations.push({ id: "validation-1", strategy_version_id: "version-1", manifest_hash: "validation-manifest-hash", state: "PASS" });
  }
  if (options.seedOpportunities) opportunities.push({ id: "opportunity-1", symbol: "EURUSD", category: "FOREX", state: "CANDIDATE", score: "0.82", score_components: { signal_quality: "0.9", data_freshness: "1", portfolio_fit: "0.6" }, reason_codes: [], risk_decision: { decision: "PASS_REDUCED", permitted_risk: "50", reason_codes: ["REDUCED_RISK_STATE_OR_SECOND_POSITION"] }, expires_at: "2026-08-14T12:15:00Z" });
  if (options.seedMonitoring) positions.push(
    { id: "position-1", provider_position_id: "mt5-position-1", symbol: "EURUSD", direction: "LONG", volume: "0.5", open_risk: "50", classification: "RECOMMENDED", matched_recommendation_id: "recommendation-1", match_confidence: "0.95", classification_reason: "RECOMMENDATION_MATCHED", opened_at: "2026-08-14T10:00:00Z", etag: '"position-position-1-1"' },
    { id: "position-2", provider_position_id: "mt5-position-2", symbol: "XAUUSD", direction: "SHORT", volume: "0.1", open_risk: "40", classification: "DISCRETIONARY", match_confidence: "0", classification_reason: "MANUAL_DISCRETIONARY_POSITION", opened_at: "2026-08-14T10:05:00Z", etag: '"position-position-2-1"' }
  );
  if (options.seedJournal) journalEntries.push({ id: "journal-1", source_type: "RECOMMENDED", symbol: "EURUSD", gross_pnl: "120", net_pnl: "110", r_multiple: "1.1", evidence: { direction: "LONG", behavior: "PLAN_FOLLOWED", entry_quality: "A", regime: "TREND", strategy_version_id: "version-1", risk_band: "LOW" }, closed_at: "2026-08-14T10:00:00Z", immutable: true, annotations: [], attachments: [] });
  let lastResearchCategory = "FOREX";
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    let body: object = { items: [] };
    if (path.endsWith("/dashboard")) {
      body = {
        account: {
          id: "account-1",
          name: "Primary demo",
          mode: "DEMO",
          currency: "USD",
          starting_balance: "100000",
          status: "ACTIVE",
          version: 1,
          etag: '"account-1"',
          prop_profile_configured: true,
          risk_policy_configured: true,
          broker_integration_id: "integration-1",
          provider_account_id: "5054425064"
        },
        risk: {
          state: "NORMAL",
          capacity: 2,
          quality: "VERIFIED",
          reason_codes: [],
          remaining_daily_margin: "2000",
          remaining_drawdown_margin: "5000",
          open_risk: "0"
        },
        metrics: {
          balance: "100000",
          equity: "100000",
          realized_pl: "0",
          floating_pl: "0",
          observed_at: "2026-08-14T00:00:00Z"
        },
        onboarding: {
          account_configured: true,
          prop_profile_configured: true,
          risk_policy_configured: true,
          account_data_verified: true
        },
        active_markets: [],
        opportunities: [],
        critical_alerts: [],
        integration_health: []
      };
    } else if (path.endsWith("/operations/health")) {
      body = {
        status: "HEALTHY",
        components: { api: "HEALTHY", database: "HEALTHY" },
        safety_impact: [],
        circuit_breakers: [],
        integration_observations: [],
        strategy_health: [],
        secrets_redacted: true
      };
    } else if (path.endsWith("/operations/audit")) {
      body = options.seedOperations ? { items: [{ id: "audit-1", action: "integration.credential.rotate", outcome: "SUCCEEDED", actor_role: "OWNER", target_type: "integration", reason: "Reconnect the read-only bridge", occurred_at: "2026-08-14T10:01:00Z", correlation_id: "correlation-1" }], append_only: true, redacted: true } : { items: [], append_only: true, redacted: true };
    } else if (path.endsWith("/jobs") && method === "GET") {
      body = { items: jobs };
    } else if (path.includes("/jobs/job-operations-1/actions") && method === "POST") {
      const requestBody = route.request().postDataJSON() as { action: string };
      const job = jobs[0];
      if (job) { job.state = requestBody.action === "PAUSE" ? "PAUSED" : job.state; job.available_actions = requestBody.action === "PAUSE" ? ["RESUME"] : []; }
      body = { ...job, idempotency_key: "job-action" };
    } else if (path.endsWith("/notifications/inbox") && method === "GET") {
      body = { items: notices, durable_critical_inbox: true };
    } else if (path.endsWith("/notifications/preferences") && method === "GET") {
      body = { items: notificationPreferences };
    } else if (path.includes("/notifications/preferences/") && method === "PUT") {
      const requestBody = route.request().postDataJSON() as { channel: string; minimum_severity: string; enabled: boolean };
      const current = notificationPreferences.find((item) => item.channel === requestBody.channel);
      const saved = { id: current?.id ?? `preference-${requestBody.channel}`, ...requestBody };
      if (current) Object.assign(current, saved); else notificationPreferences.push(saved);
      body = saved;
    } else if (path.includes("/notifications/channels/") && path.endsWith("/test") && method === "POST") {
      const channel = path.split("/").at(-2) ?? "WEB";
      notices.push({ id: `notice-${channel}`, event_type: "NOTIFICATION_CHANNEL_TEST", severity: "INFO", payload: { title: `${channel} channel test`, message: "TraderX notification test completed." }, state: "DELIVERED", read_at: null, created_at: "2026-08-14T10:02:00Z" });
      body = { event_id: `event-${channel}`, channel, state: channel === "WEB" ? "DELIVERED" : "QUEUED", web_inbox_copy: true };
    } else if (path.includes("/notifications/inbox/") && path.endsWith("/read") && method === "POST") {
      const notice = notices.find((item) => item.id === path.split("/").at(-2));
      if (notice) { notice.state = "READ"; notice.read_at = "2026-08-14T10:03:00Z"; }
      body = notice ?? {};
    } else if (path.endsWith("/journal/analytics")) {
      const dimension = new URL(route.request().url()).searchParams.get("dimension") ?? "instrument";
      const group = dimension === "behavior" ? "PLAN_FOLLOWED" : dimension === "asset_class" ? "FOREX" : "EURUSD";
      body = options.seedJournal ? { dimension, entry_count: 1, groups: { [group]: { count: 1, net_pnl: "110", r: "1.1" } } } : { dimension, entry_count: 0, groups: {} };
    } else if (path.endsWith("/journal/entries") && method === "GET") {
      body = { items: journalEntries };
    } else if (path.endsWith("/journal/project") && method === "POST") {
      body = { created: 0, append_only: true };
    } else if (path.includes("/journal/entries/journal-1/annotations") && method === "POST") {
      const requestBody = route.request().postDataJSON() as { content: string };
      const entry = journalEntries[0] as { annotations: Array<Record<string, unknown>> } | undefined;
      entry?.annotations.push({ id: "annotation-1", content: requestBody.content, supersedes_id: null, created_at: "2026-08-14T10:10:00Z" });
      body = { id: "annotation-1", entry_id: "journal-1", content: requestBody.content, append_only: true };
    } else if (path.includes("/journal/entries/journal-1/attachments") && method === "POST") {
      const entry = journalEntries[0] as { attachments: Array<Record<string, unknown>> } | undefined;
      entry?.attachments.push({ id: "attachment-1", original_name: "chart.png", media_type: "image/png", checksum: "abcdef1234567890", download_path: "/api/v1/journal/attachments/attachment-1" });
      body = { id: "attachment-1", entry_id: "journal-1", protected: true, checksum: "abcdef1234567890", download_path: "/api/v1/journal/attachments/attachment-1" };
    } else if (path.endsWith("/journal/proposals") && method === "POST") {
      body = { id: "proposal-1", hypothesis: "Test trend entries after planned pullbacks", evidence_links: ["journal:journal-1"], state: "PROPOSED", source_strategy_mutated: false };
    } else if (path.endsWith("/integrations")) {
      body = mt5Integrations;
    } else if (path.includes("/integrations/integration-1/mt5/enrollment") && method === "POST") {
      body = { ...mt5Integrations[0], enrollment: { agent_id: "agent-operations-1", code: "rotated-operations-setup-code", expires_at: "2026-08-15T10:00:00Z" } };
    } else if (path.endsWith("/market-rotation/recommendations")) {
      body = options.seedActiveMarket ? { items: [{ category: "FOREX", current: { instrument_id: "instrument-FOREX", symbol: "EURUSD", score: "0.71" }, candidate: { instrument_id: "instrument-GBPUSD", candidate_assessment_id: "candidate-GBPUSD", symbol: "GBPUSD", score: "0.83" }, recommended: true, improvement: "0.12", reason_codes: ["CANDIDATE_MATERIALLY_BETTER"] }], requires_human_replacement_review: true } : { items: [], requires_human_replacement_review: true };
    } else if (path.endsWith("/market-rotation/history")) {
      body = { items: activeMarkets.map((item) => ({ ...item, effective_from: "2026-08-14T00:00:00Z", effective_to: null, approval_reason: "Approved fixture" })) };
    } else if (path.includes("/market-rotation/instruments/") && path.endsWith("/reactivation")) {
      body = { instrument_id: path.split("/").at(-2), symbol: "EURUSD", current_status: "INACTIVE", state: "REVALIDATION_REQUIRED", workflow_state: method === "POST" ? "REVALIDATION_REQUIRED" : undefined, steps: ["REFRESH_MISSING_INTERVALS", "SELECTIVE_VALIDATION", "HUMAN_APPROVAL"], data_gaps: [{ kind: "HISTORICAL_COVERAGE", required_observations: 30 }], knowledge: { aliases: 2, strategies: 1, strategy_versions: 3, journal_entries: 8, research_experiments: 2 }, ends_in_human_approval: true, automatically_activated: false, ...(method === "POST" ? { job: { id: "reactivation-job-1", state: "COMPLETED" } } : {}) };
    } else if (path.endsWith("/markets/instruments")) {
      const category = new URL(route.request().url()).searchParams.get("category") ?? "FOREX";
      const symbol = symbols[category];
      body = { items: symbol ? [{ id: `instrument-${category}`, symbol, display_name: `${category} candidate`, category, status: activeMarkets.some((item) => item.category === category) ? "ACTIVE" : "INACTIVE", data_status: "VERIFIED", version: 1, quality_observed_at: "2026-08-14T00:00:00Z", quality_reason_codes: [] }] : [] };
    } else if (path.endsWith("/markets/active") && method === "GET") {
      body = { items: activeMarkets, maximum: 3 };
    } else if (path.endsWith("/markets/research") && method === "POST") {
      const requestBody = route.request().postDataJSON() as { category?: string };
      lastResearchCategory = requestBody.category ?? "FOREX";
      body = { id: `job-${lastResearchCategory}`, run_id: `run-${lastResearchCategory}`, state: "COMPLETED" };
    } else if (path.includes("/markets/research/run-")) {
      const symbol = symbols[lastResearchCategory];
      body = { id: `run-${lastResearchCategory}`, category: lastResearchCategory, state: "COMPLETED", methodology_version: "market-suitability-v1", input_manifest_hash: "evidence-hash", completed_at: "2026-08-14T00:00:00Z", ranking_is_not_activation: true, candidates: [{ id: `candidate-${lastResearchCategory}`, instrument_id: `instrument-${lastResearchCategory}`, symbol, display_name: `${lastResearchCategory} candidate`, eligible: true, score: "0.82", rank: 1, confidence: "0.91", exclusions: [], components: { volatility: "0.8", liquidity: "0.9", cost_quality: "0.7" } }] };
    } else if (path.includes("/markets/active/") && method === "PUT") {
      const category = path.split("/").at(-1) ?? "FOREX";
      const current = activeMarkets.find((item) => item.category === category);
      const assignment = { id: current?.id ?? `active-${category}`, instrument_id: `instrument-${category}`, symbol: symbols[category], category, state: "ACTIVE", version: (current?.version ?? 0) + 1, etag: `"active-${category}-${(current?.version ?? 0) + 1}"` };
      if (current) Object.assign(current, assignment); else activeMarkets.push(assignment);
      body = assignment;
    } else if (path.includes("/markets/active/") && method === "DELETE") {
      const category = path.split("/").at(-1) ?? "FOREX";
      const index = activeMarkets.findIndex((item) => item.category === category);
      const removed = index >= 0 ? activeMarkets.splice(index, 1)[0] : undefined;
      body = { id: removed?.id, category, state: "DEACTIVATED", deactivated: true };
    } else if (path.endsWith("/strategies") && method === "GET") {
      body = { items: strategies };
    } else if (path.endsWith("/strategies") && method === "POST") {
      const requestBody = route.request().postDataJSON() as { name: string; instrument_id: string; definition: Record<string, unknown>; change_summary: string };
      const version = { id: "version-1", strategy_id: "strategy-1", sequence: 1, row_version: 1, definition: requestBody.definition, definition_hash: "strategy-definition-hash-v1", lifecycle: "DRAFT", parent_version_id: null, change_summary: requestBody.change_summary, created_at: "2026-08-14T00:00:00Z", etag: '"strategy-version-version-1-1"', immutable: true };
      const strategy = { id: "strategy-1", name: requestBody.name, instrument_id: requestBody.instrument_id, version: 1, etag: '"strategy-strategy-1-1"', versions: [version], created_version: version };
      strategies.splice(0, strategies.length, strategy);
      body = strategy;
    } else if (path.endsWith("/validation/backtests") && method === "POST") {
      body = { job: { id: "backtest-job-1", state: "COMPLETED" }, run: { id: "backtest-1", state: "PASS", manifest_hash: "backtest-manifest-hash", execution_model_version: "execution-v1", metrics: { trades: 12, net_pnl: "325", average_r: "0.85", maximum_drawdown: "120", total_costs: "18", maximum_mae: "45", maximum_mfe: "92", equity_curve: ["100000", "100325"], r_distribution: ["0.85"] } } };
    } else if (path.endsWith("/validation/runs") && method === "POST") {
      body = { job: { id: "validation-job-1", state: "COMPLETED" }, run: { id: "validation-1", state: "PASS", manifest_hash: "validation-manifest-hash", seed: 20260813, evidence: { out_of_sample: { state: "PASS", observations: 12 }, walk_forward: { state: "PASS", windows: 3 }, parameter_stability: { state: "STABLE", trials: 5 }, monte_carlo: { state: "PASS", trials: 300 }, portfolio: { state: "PASS", maximum_positions: 2 }, reason_codes: [] } } };
    } else if (path.endsWith("/validation/runs") && method === "GET") {
      body = { items: validations };
    } else if (path.endsWith("/paper/runs") && method === "POST") {
      const run = { id: "paper-run-1", strategy_version_id: "version-1", validation_run_id: "validation-1", state: "AWAITING_APPROVAL", metrics: { trades: 24, duration_days: 21, paper_expectancy: "0.72", historical_expectancy: "0.75", net_pnl: "720" }, criteria: { eligible: true, reason_codes: [], minimum_trades: 20, minimum_duration_days: 14 }, comparison: { divergence: "0.03", disposition: "AWAITING_APPROVAL" }, history: [{ id: "paper-trade-1", direction: "LONG", entry: "1.08", exit: "1.09", pnl: "100" }] };
      paperRuns.splice(0, paperRuns.length, run);
      body = { job: { id: "paper-job-1", state: "COMPLETED" }, run };
    } else if (path.endsWith("/paper/runs") && method === "GET") {
      body = { items: paperRuns };
    } else if (path.includes("/approvals/strategies/") && method === "POST") {
      body = { id: "approval-1", strategy_version_id: "version-1", paper_run_id: "paper-run-1", decision: "APPROVE_LIVE", evidence_hash: "paper-evidence-hash", reason: "Evidence is current and within limits", decided_at: "2026-08-14T00:00:00Z" };
    } else if (path.endsWith("/opportunities") && method === "GET") {
      body = { items: opportunities, risk_authorization_is_separate: true, no_execution_capability: true };
    } else if (path.endsWith("/opportunities/evaluate") && method === "POST") {
      body = { items: opportunities, idempotency_key: "fixture", no_execution_capability: true };
    } else if (path.includes("/opportunities/opportunity-1/recommendation") && method === "GET") {
      body = { id: "recommendation-1", opportunity_id: "opportunity-1", state: "ISSUED", entry: "1.085", stop: "1.08", targets: ["1.095"], volume: "0.5", invalidation: { type: "REGIME_CHANGE" }, reason_trace: { risk_decision: "PASS_REDUCED", direction: "LONG", score: "0.82" }, expires_at: "2026-08-14T12:15:00Z", manual_execution_only: true, no_execution_capability: true };
    } else if (path.endsWith("/positions") && method === "GET") {
      body = { items: positions, broker_mode: "READ_ONLY", no_execution_capability: true };
    } else if (path.endsWith("/positions/refresh") && method === "POST") {
      body = { status: "COMPLETED", accounts_refreshed: 1, broker_mode: "READ_ONLY" };
    } else if (path.includes("/positions/position-1/thesis") && method === "GET") {
      body = { position_id: "position-1", immutable: true, thesis: { id: "thesis-1", frozen_evidence: { entry: "1.085", stop: "1.08", targets: ["1.095"], invalidation: { type: "REGIME_CHANGE" }, reason_trace: { score: "0.82" } }, created_at: "2026-08-14T10:00:00Z" }, observations: [{ id: "observation-1", health: "HEALTHY", evidence: { current_price: "1.087" }, observed_at: "2026-08-14T10:05:00Z" }] };
    } else if (path.includes("/positions/position-2/thesis") && method === "GET") {
      body = { position_id: "position-2", immutable: true, thesis: null, observations: [] };
    } else if (path.includes("/positions/") && path.endsWith("/classification") && method === "PUT") {
      const positionId = path.split("/").at(-2);
      const position = positions.find((item) => item.id === positionId);
      const requestBody = route.request().postDataJSON() as { classification: string };
      if (position) { position.classification = requestBody.classification; position.classification_reason = "USER_CORRECTION"; }
      body = { ...position, audited: true };
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}
