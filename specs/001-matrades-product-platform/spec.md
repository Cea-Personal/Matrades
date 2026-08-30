# Feature Specification: Matrades Product Platform

**Feature Branch**: Not created (no `before_specify` hook configured)

**Created**: 2026-08-23

**Status**: Draft

**Input**: Merge the three supplied Matrades product specifications with the supplied
account-equity, remaining-risk-capacity, correlated-risk, agent-registry, and independent
prompt-resolution clarifications into one non-repetitive product specification.

## Clarifications

### Session 2026-08-24

- Q: Should LiteLLM require explicit operator selection, or may Matrades automatically fall back to it when the primary Codex runtime is unavailable? → A: Codex is the default for every required agent; LiteLLM is explicit opt-in per agent or model profile, with no automatic cross-runtime fallback.

### Session 2026-08-25

- Q: Should Matrades select one research candidate per asset class, or one per asset-class and instrument-type combination? → A: One candidate for every supported asset-class and instrument-type combination in each daily research cycle. The initial matrix covers Forex, metals, cryptocurrency, and stocks across spot, CFD, and futures, including metals CFD and cryptocurrency CFD. Spot represents cash or underlying ownership, CFD represents a derivative exposure, and futures represent contract exposure.
- Q: After deterministic policy and risk checks pass, which parts of the trade lifecycle may Matrades execute autonomously without HIL approval? → A: Full lifecycle automation with per-account controls: Matrades may place and cancel orders, set or modify Stop Loss and Take Profit, partially close positions, and fully exit positions without HIL approval, subject to deterministic hard limits, explicit per-account permissions, complete audit logging, and an emergency kill switch.
- Q: May the new knowledge-and-journal AI agent trigger trades or change live positions through chat, or should it only answer questions? → A: The agent is read-only: it answers from authorized knowledge and journal evidence with citations and cannot trigger, prepare, modify, or execute trades.
- Q: When should live trade-journal content become searchable by the Knowledge Assistant? → A: Immutable journal events are indexed into knowledge continuously during the active trade, the structured journal remains authoritative, and a consolidated summary is indexed when the trade closes.
- Q: What actions should users be able to perform from an embedded live chart? → A: The chart is interactive but read-only, with live prices, indicators, and overlays for the trade plan, fills, Stop Loss and Take Profit, journal events, and automated actions; it cannot create execution requests or broker writes.
- Q: How should Matrades present backtest, paper-trading, and live-trading results in performance analytics? → A: Keep backtest, paper-trading, and live-trading analytics as separate evidence classes, allow filtered side-by-side comparison, and default operational analytics to live results without blending simulated and live headline metrics.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute a Safe Automated Trade (Priority: P1)

As a trader, I want Matrades to turn current market, account, policy, and strategy evidence
into a risk-checked trade plan and execute it automatically within the permissions configured
for that account.

**Why this priority**: Safe automated execution is the product's primary value and the point at
which inaccurate data, duplicate commands, or weak enforcement can cause direct financial harm.

**Independent Test**: Configure one account, one eligible strategy, current market and account
snapshots, applicable limits, and entry permission; verify that an eligible plan is executed once
with a complete risk snapshot while an over-limit plan is blocked before any broker write.

**Acceptance Scenarios**:

1. **Given** current authoritative data, a validated eligible strategy, and sufficient remaining
   capacity, **When** a candidate trade passes policy, risk, and critic review, **Then** the user
   receives a visible trade plan and Matrades submits exactly one broker order when the account's
   entry permission is enabled.
2. **Given** a candidate's worst-case loss would breach any applicable hard limit, **When** the
   candidate is evaluated, **Then** it is HARD BLOCKED before execution and the breached limit and
   source are shown.
3. **Given** a valid setup whose original size exceeds available capacity, **When** a smaller
   size can comply with every limit, **Then** the result is REDUCE SIZE with the compliant size
   and updated risk snapshot.

---

### User Story 2 - Research Markets for the Session (Priority: P1)

As a trader, I want one ranked candidate for every supported asset-class and instrument-type
combination so that Matrades can autonomously establish the session's research universe across
Forex, metals, cryptocurrency, and stocks in spot, CFD, and futures markets.

**Why this priority**: Market selection bounds all later analysis while allowing the configured
automation pipeline to operate without a human approval queue.

**Independent Test**: Run daily research with healthy sources, verify one ranked recommendation
for every supported asset-class and instrument-type combination continues into analysis without
approval, and verify an ineligible first-ranked candidate falls back safely or produces NO TRADE.

**Acceptance Scenarios**:

1. **Given** healthy required sources, **When** each daily research cycle completes, **Then**
   Matrades recommends one instrument for every supported Forex, metals, cryptocurrency, and
   stocks spot, CFD, and futures combination and continues eligible candidates into analysis.
2. **Given** a first-ranked candidate becomes ineligible before analysis, **When** another ranked
   candidate still satisfies the configured universe, freshness, and eligibility rules, **Then**
   Matrades records the invalidation and continues with the next eligible candidate without approval.
3. **Given** no eligible market has adequate evidence, **When** research completes, **Then**
   Matrades reports NO TRADE or DEGRADED rather than forcing a recommendation.

---

### User Story 3 - Execute and Manage a Trade Automatically (Priority: P1)

As a trader, I want Matrades to execute an authorized trade plan, reconcile the broker result, and
manage the live position automatically within account-specific permissions and hard risk limits.

**Why this priority**: Full lifecycle automation is reliable only when requested actions are
reconciled to actual broker state and every write remains bounded, idempotent, and auditable.

**Independent Test**: Authorize full lifecycle automation for one test account, execute a plan,
reconcile the fill, automatically modify protection, partially close, and fully exit; verify each
action occurs once, respects hard limits, is audited, and is stopped by the account kill switch.

**Acceptance Scenarios**:

1. **Given** an executable plan and enabled entry permission, **When** the broker accepts the order,
   **Then** Matrades records the broker order and does not represent it as a live position until a
   fill is confirmed.
2. **Given** the broker reports the resulting position, **When** reconciliation succeeds, **Then**
   actual entry, size, protections, fees, and P&L become authoritative for monitoring.
3. **Given** monitoring recommends a partial profit, Stop Loss move, or discretionary exit,
   **When** the relevant account permission is enabled and deterministic checks pass, **Then**
   Matrades executes the action once and records its reason, inputs, request, and broker result.
4. **Given** the emergency kill switch is active, **When** any new entry or discretionary position
   change is requested, **Then** the request is blocked before broker submission while existing
   broker-hosted protective orders remain intact.
5. **Given** a reconciled active position, **When** the user opens it, **Then** its complete current
   trade plan is visible alongside an interactive live chart showing actual fills, protections,
   journal events, and automated management actions.
6. **Given** the user pans, zooms, changes timeframe, or applies a supported indicator, **When** the
   chart updates, **Then** the interaction changes only the view and creates no execution request or
   broker command.
7. **Given** the broker confirms an entry order or fill, **When** Matrades records the execution,
   **Then** it sends one deduplicated trade-entry notification through every enabled channel with the
   account, instrument, side, actual or pending quantity, price or order level, protections, strategy,
   and Trade Plan link.

---

### User Story 4 - Create and Validate a Strategy (Priority: P2)

As a trader or researcher, I want the Strategy Researcher to generate a strategy autonomously or
the Strategy Assistant to turn my description into a complete proposal, then move the approved
proposal through one evidence-based lifecycle so that origin never substitutes for quality.

**Why this priority**: Reusable validated strategies are necessary for disciplined proposals,
but the trade-decision workflow can first operate with a seeded validated strategy.

**Independent Test**: Generate one autonomous proposal and one proposal from a partial natural-
language idea, review their family and step-by-step rules, approve one into the canonical
repository, detect similarity, validate it, and verify that it cannot become live before all
required stages pass.

**Acceptance Scenarios**:

1. **Given** an incomplete user idea, **When** AI assistance is requested, **Then** the Strategy
   Assistant selects or confirms a family and returns a complete step-by-step proposal that remains
   non-canonical until the user explicitly approves it.
2. **Given** a strategy materially equivalent to an existing one, **When** similarity analysis
   completes, **Then** Matrades offers reuse, comparison, version, or variant actions instead of
   silently creating a duplicate.
3. **Given** any newly created strategy, **When** live activation is attempted before
   validation and paper trading complete, **Then** activation is prevented with the remaining
   stages shown.
4. **Given** an active strategy, **When** Improve with AI is selected, **Then** a separate draft is
   created and the active version remains unchanged.

---

### User Story 5 - Configure Accounts, Rules, and Security (Priority: P2)

As a trader, I want to configure accounts, prop-firm rules, internal guardrails, credentials, and
connections through the product so that routine operation is secure and account-specific.

**Why this priority**: Trading decisions cannot be trusted until the active account and its exact
restrictions are known and protected configuration is available.

**Independent Test**: Enroll with MFA, add a prop account and versioned ruleset, set stricter
internal limits, save a connection credential, reload the configuration, and verify the effective
limits and masked secret.

**Acceptance Scenarios**:

1. **Given** a prop account, **When** external and internal limits overlap, **Then** the strictest
   effective value, source, and reason are displayed.
2. **Given** a saved secret, **When** any configuration view is reopened, **Then** only a masked
   representation is shown and the secret is absent from prompts, logs, and exports.
3. **Given** a sensitive risk, credential, or security change, **When** the user attempts to save
   it, **Then** step-up authentication is required and the change is audited.

---

### User Story 6 - Configure Agents Without Changing Their Authority (Priority: P2)

As an operator, I want every required logical agent to use the Codex-hosted runtime by default while
allowing an explicit LiteLLM alternative per agent or model profile, so that I can tune quality,
cost, and resilience without silent runtime switching or changes to permissions and workflow identity.

**Why this priority**: Model independence and clear prompt inheritance prevent vendor lock-in and
configuration surprises while preserving stable safety boundaries.

**Independent Test**: Verify every required agent resolves to the Codex-hosted runtime by default;
explicitly opt one agent into a LiteLLM-backed profile, assign an agent-specific system prompt while
its user prompt inherits, exercise a same-runtime compatible fallback, and verify the actual runtime,
model, prompts, and fallback are recorded without permission changes or cross-runtime fallback.

**Acceptance Scenarios**:

1. **Given** a required agent without an explicit alternative runtime selection, **When** the agent
   runs, **Then** it executes on the Codex-hosted runtime.
2. **Given** an agent system-prompt override and user-prompt inheritance, **When** the agent runs,
   **Then** it uses the agent system prompt and the orchestrator user prompt.
3. **Given** no agent or orchestrator prompt for one prompt type, **When** the agent runs, **Then**
   that prompt type resolves to the platform default independently of the other type.
4. **Given** an operator explicitly assigns a LiteLLM-backed profile to an agent, **When** the agent
   runs, **Then** LiteLLM is used and the explicit runtime selection is visible in configuration and
   audit history.
5. **Given** the primary model is unavailable and a compatible fallback is configured in the same
   selected runtime, **When** the agent runs, **Then** that fallback is used and audited without
   switching between Codex and LiteLLM.
6. **Given** a runtime, model, or prompt change, **When** it is saved, **Then** agent tool permissions remain
   unchanged.

---

### User Story 7 - Retrieve Context Without Replacing Facts (Priority: P3)

As a trader or research agent, I want a read-only Knowledge Assistant to answer questions from
relevant strategy, source-document, journal, and research context with provenance so that prior
knowledge helps understanding without replacing current structured facts or creating trading actions.

**Why this priority**: Knowledge retrieval improves research quality, but core trading safety must
remain functional without it.

**Independent Test**: Ask the Knowledge Assistant a question whose answer requires one strategy
note and one journal entry, verify authorization and source citations, attempt to prompt it to place
or modify a trade and confirm that no trade plan or broker command is created, then disable retrieval
and confirm deterministic risk and policy decisions continue safely.

**Acceptance Scenarios**:

1. **Given** related historical strategy research, **When** a new hypothesis is assessed, **Then**
   relevant records may inform review but the final similarity result also uses canonical rules.
2. **Given** a prop-firm source passage, **When** a possible rule is extracted, **Then** it remains
   non-authoritative until reviewed, structured, versioned, verified, and activated.
3. **Given** unavailable semantic retrieval, **When** a risk decision is required, **Then** the Risk
   Engine does not use retrieved content and continues or blocks solely according to authoritative
   data health.
4. **Given** an authorized user asks about prior trading behavior, **When** the Knowledge Assistant
   answers, **Then** each material factual claim links to the journal or knowledge segments used.
5. **Given** any conversational instruction to enter, cancel, modify, partially close, or fully exit
   a trade, **When** the Knowledge Assistant processes it, **Then** it refuses the trading action and
   creates no executable trade plan, execution-service request, or broker command.

---

### User Story 8 - Review Decisions and Performance (Priority: P3)

As a trader, I want a complete journal, performance views, health states, and automation operations
view so that I can understand what happened, respond to urgent conditions, and improve through
controlled research.

**Why this priority**: Audit and learning close the feedback loop after safe research and trading
workflows exist.

**Independent Test**: Complete a simulated trade lifecycle while the Journal agent records live
monitoring observations, query those events through the Knowledge Assistant before the trade closes,
verify the post-trade summary and provenance after close, reconstruct the inputs and decisions, and
confirm that degradation creates research or suspension work rather than silently changing a live
strategy.

**Acceptance Scenarios**:

1. **Given** a completed trade, **When** its journal is opened, **Then** the user can trace the
   plan, execution, actual position, live monitoring observations, management decisions, versions,
   outcome, and evidence.
2. **Given** an active strategy with degraded recent performance, **When** health evaluation runs,
   **Then** Matrades may flag or suspend it and may initiate research but does not mutate its rules.
3. **Given** multiple automated workflows and open positions, **When** the operations view opens,
   **Then** active plans, executions, monitoring actions, hard blocks, and kill-switch state are
   grouped by account and urgency is clear.
4. **Given** a reconciled active position, **When** monitoring receives a material market, account,
   risk, strategy, execution, or position-state event, **Then** the Journal agent appends a timestamped
   observation and its evidence without rewriting earlier entries.
5. **Given** a committed live journal event, **When** its knowledge index is healthy, **Then** the
   event becomes searchable during the active trade and links back to the authoritative journal event.
6. **Given** a trade reaches a terminal state, **When** journaling finalizes it, **Then** the Journal
   agent creates and indexes a consolidated post-trade summary without replacing the underlying events.
7. **Given** backtest, paper-trading, and live results exist for one strategy, **When** performance
   analytics opens, **Then** live results are selected by default and each evidence class has separate
   headline metrics with an optional side-by-side comparison.
8. **Given** a user inspects the reported edge, **When** the metric is expanded, **Then** Matrades
   shows after-cost expectancy, sample size, observation period, uncertainty, and the contributing
   trades without mixing evidence classes.

### Edge Cases

- A current-equity snapshot is missing, stale, from the wrong account, or older than other position
  events required for the decision.
- Current balance is positive while current equity or remaining daily capacity is insufficient.
- Unrealized profit appears to create capacity, but the active policy does not permit using it.
- An open position has no Stop Loss, has a Stop Loss beyond the entry risk, or has an unconfirmed
  broker update; its reserved loss cannot be established safely.
- A candidate fits under the concurrent-trade ceiling but breaches portfolio, market-category, or
  correlated-exposure limits.
- Multiple open positions create indirect or opposing exposures that cannot be confidently grouped.
- A prop-firm source changes after a trade decision; historical records must keep the older ruleset.
- Prop-firm and internal limits use different currencies, reset times, or drawdown bases.
- More than one approved proposal could match a newly detected broker position.
- Broker, bridge, calendar, or market data disconnects while a position remains open.
- The chart stream is delayed, disconnected, or uses a symbol mapping or timeframe inconsistent with
  the active broker position; the chart must display the mismatch and must not imply current state.
- An agent's primary and fallback models both lack a required capability.
- The Codex-hosted runtime is unavailable for an agent that has not been explicitly assigned a
  LiteLLM alternative; the agent becomes DEGRADED or BLOCKED and does not switch runtimes silently.
- Only one of the agent's system or user prompt types is overridden.
- Retrieved knowledge belongs to another user or account or conflicts with a verified structured rule.
- An AI proposal is malformed, incomplete, duplicated, or includes unsupported semantics.
- A strategy's parameter-only change is submitted as a new identity, or a material rule change is
  submitted as a profile update.
- No validated strategy matches the current market regime.
- A broker-side Stop Loss or Take Profit executes while an automated modification request is in flight.
- A broker response times out after accepting an order, so Matrades must reconcile before retrying.
- An account permission or kill-switch state changes while an execution request is in flight.

## Requirements *(mandatory)*

### Scope

Matrades V1 covers AI-assisted research and full-lifecycle automated trading for Forex, metals, cryptocurrency,
and stocks across supported spot, CFD, and futures instruments. It includes secure user access,
UI-managed configuration, provider-neutral data and broker connections, agent orchestration,
market research, strategy creation and validation, account-specific deterministic risk and policy
enforcement, automated execution and position management, monitoring, journaling, performance analysis,
notifications, health, and auditability.

The default V1 excludes high-frequency or market-making execution, latency-sensitive
arbitrage execution, hard-rule overrides by AI or users, and live recommendations from strategies
that have not completed the required validation lifecycle.

This scope removes HIL-1, HIL-2, and HIL-3 and requires a major constitutional amendment before
dependent planning or implementation can be considered constitutionally compliant.

### Functional Requirements

#### Automated Daily Workflow

- **FR-001**: Matrades MUST operate without HIL-1, HIL-2, or HIL-3 approval gates; no market-selection,
  entry, modification, partial-close, or exit action may depend on a routine human approval step.
- **FR-002**: Each daily research cycle MUST normally present one ranked candidate for every supported
  combination of asset class (Forex, metals, cryptocurrency, and stocks) and instrument type
  (spot, CFD, and futures), including metals CFD and cryptocurrency CFD, and MUST continue eligible
  candidates into the configured analysis pipeline without waiting for approval.
- **FR-003**: The number of researched instruments MUST NOT imply the number of trades permitted.
- **FR-004**: After strategy, data-freshness, policy, guardrail, account-equity, portfolio-risk, and
  critic checks pass, Matrades MUST submit an entry order only when that account's entry permission
  is enabled and MUST NOT require a human approval.
- **FR-005**: Matrades MUST support autonomous order cancellation, Stop Loss and Take Profit creation
  or modification, partial close, exposure reduction, early exit, and full exit when the specific
  action is enabled for the account and all deterministic hard checks pass.
- **FR-006**: Broker-side protective Stop Loss and Take Profit execution MUST be recognized without
  requiring an additional human decision.
- **FR-007**: WAIT, NO TRADE, BLOCK, and DEGRADED MUST be supported as valid, visible outcomes.

#### Identity, Security, and Configuration

- **FR-008**: Account activation MUST require primary signup, email verification, multi-factor
  enrollment, and recovery-code issuance; every sign-in MUST include an MFA challenge.
- **FR-009**: The initial MFA experience MUST support authenticator-app one-time codes and MUST
  preserve a path for additional strong authentication methods later.
- **FR-010**: Credential, broker, risk-limit, hard-rule, and security changes MUST require step-up
  authentication and MUST produce an audit event.
- **FR-011**: Routine configuration MUST be available through the UI without requiring source or
  deployment changes, including named Twelve Data, Coinbase, CoinGecko, FRED, calendar, news, and
  execution-capable MT5 Bridge connection profiles.
- **FR-012**: Stored secrets MUST be encrypted, displayed in full only during initial entry, masked
  thereafter, excluded from logs and model prompts, and accessed only by authorized reference.
- **FR-013**: Users MUST be able to replace and test credentials without exposing the saved value;
  a connection test MUST perform a bounded provider or MT5 Bridge health probe and MUST NOT
  fabricate a healthy result.
- **FR-014**: Authorization MUST isolate each user's accounts, strategies, journal, research, and
  knowledge unless explicit sharing is later authorized.

#### Accounts, Prop-Firm Rules, and Guardrails

- **FR-015**: A trading account MUST identify whether it is personal or prop-firm, its currency,
  broker connection, platform, execution mode, applicable guardrail profile, and status.
- **FR-016**: Prop-firm configuration MUST distinguish firm, program, account type, account size
  where applicable, versioned ruleset, and trading account.
- **FR-017**: A ruleset MUST retain its source, effective date, verification state, last verification
  date, enforcement level, and version; historical decisions MUST retain the version used.
- **FR-018**: Rules MUST support daily loss, total and trailing drawdown, risk per trade, news and
  event restrictions, prohibited styles, holding restrictions, instruments, sessions, and
  consistency requirements where applicable.
- **FR-019**: Users MUST be able to configure internal daily, weekly, and total loss limits; trade,
  portfolio, correlated, and market-category exposure; position and trade-count ceilings; minimum
  Risk:Reward; consecutive-loss limits; session/event restrictions; and freshness requirements.
- **FR-020**: For overlapping constraints, Matrades MUST apply the most restrictive applicable
  prop-firm, global, account, strategy, or internal rule and show its value, source, and reason.
- **FR-021**: Extracted or retrieved prop-firm rules MUST remain non-authoritative until a user
  reviews, structures, verifies, versions, and activates them.

#### Account Equity and Remaining Risk Capacity

- **FR-022**: Current broker/account equity MUST be a mandatory input to every pre-trade eligibility
  and position-size decision; original balance or nominal account size alone MUST NOT suffice.
- **FR-023**: Every candidate evaluation MUST retrieve or calculate starting account balance,
  current balance, current equity, floating P&L, realized daily P&L, current drawdown, daily
  drawdown, maximum permitted drawdown, prop-firm drawdown limit, internal drawdown limit, existing
  open-trade risk, correlated exposure, remaining daily loss capacity, remaining total loss
  capacity, and remaining portfolio-risk capacity.
- **FR-024**: Reserved risk MUST equal the sum of remaining worst-case losses to the current Stop
  Loss across open positions and MUST reduce the capacity available to candidate trades.
- **FR-025**: Unrealized profit MUST NOT automatically increase available risk capacity unless the
  active policy explicitly permits and defines that treatment.
- **FR-026**: The Risk Engine MUST evaluate account equity, drawdown capacity, daily loss capacity,
  reserved risk, portfolio and correlated exposure, candidate risk, prop-firm restrictions,
  internal guardrails, and the concurrent-trade ceiling in that authority order before execution.
- **FR-027**: A candidate MUST be HARD BLOCKED if its worst-case loss would breach any applicable
  hard limit.
- **FR-028**: The Risk Engine MUST return PASS, REDUCE SIZE, or HARD BLOCK and MUST identify the
  limiting constraint and projected post-trade exposure.
- **FR-029**: If REDUCE SIZE is returned, the reduced position MUST satisfy every applicable hard
  limit and the proposal MUST use the reduced values.
- **FR-030**: The effective number of additional trades MUST be calculated dynamically from current
  equity, remaining drawdown and daily-loss capacity, existing positions and reserved risk,
  candidate risk, portfolio, correlated and market-category exposure, prop-firm restrictions,
  internal guardrails, and the static concurrent-trade ceiling.
- **FR-031**: A candidate MAY be blocked below the concurrent-trade ceiling when aggregate,
  category, or correlated exposure is insufficient; open positions MUST NOT automatically be
  treated as independent risk events.
- **FR-032**: Every executable trade plan MUST include a pre-trade equity snapshot showing account equity, starting
  balance, current and maximum drawdown, remaining drawdown, daily loss used and remaining,
  existing open risk, candidate risk, projected portfolio risk, open-trade count, concurrent-trade
  ceiling, additional-trade capacity, and the Risk Engine result.
- **FR-033**: Missing, stale, mismatched, or internally inconsistent account state MUST block a new
  actionable proposal whenever accurate worst-case risk cannot be established.

#### Market Data, Research, and Analysis

- **FR-034**: External market, macro, positioning, calendar, news, broker, and crypto-discovery
  providers MUST be replaceable without changing agent or trading rules.
- **FR-035**: The initial provider set MUST support configured authoritative mappings for each
  enabled Forex, metals, cryptocurrency, and stocks asset-class and instrument-type combination;
  it MUST retain Twelve Data for Forex and metals where applicable, Coinbase for crypto exchange
  data, CoinGecko for broad crypto discovery, FRED for macro data, CFTC COT for positioning,
  configurable calendar and news sources, and broker or MT5 state.
- **FR-036**: Coinbase-derived crypto data MUST be normalized before agent use and, where available,
  cover instruments, prices, trades, candles, bid/ask, order-book depth, live updates, and history.
- **FR-037**: CoinGecko MUST remain a separate broad-discovery and asset-metadata source rather than
  the authoritative exchange-level source.
- **FR-038**: Current prices, candles, timestamps, broker/account state, positions, risk, policy,
  strategy status, and performance metrics MUST come from authoritative structured records, not
  model output or semantic retrieval.
- **FR-039**: Market records MUST retain source, timestamp, freshness, and normalization status;
  strategies that depend on stale critical inputs MUST be disabled or blocked according to policy.
- **FR-040**: Calendar ingestion MUST normalize event time, importance, affected country or currency,
  previous value, forecast, and actual value where available and MUST expose source health.
- **FR-041**: Daily research MUST rank candidates using applicable volatility, spread, liquidity,
  trend clarity, session conditions, strategy opportunity, event risk, macro context, and data
  quality evidence. Every successful, degraded, or failed market-research cycle MUST write an
  immutable timestamped archive manifest and link its path and checksum to the durable run.
- **FR-042**: Active-market analysis MUST support technical, structure, liquidity, fundamental,
  event, sentiment/positioning, volatility, and relevant intermarket evidence.
- **FR-043**: Regime classification MUST produce a structured market fingerprint capable of
  representing trend direction, range, volatility state, compression/expansion, post-event state,
  risk-on/risk-off, and unstable or conflicting evidence.

#### Agents, Models, Prompts, and Tools

- **FR-044**: The initial required logical agent registry MUST contain `orchestrator`,
  `forex_research`, `metals_research`, `crypto_research`, `technical_analyst`,
  `fundamental_analyst`, `sentiment_analyst`, `regime_analyst`, `strategy_selector`,
  `strategy_researcher`, `strategy_assistant`, `critic`, `trade_monitor`, `journal`, and
  `performance`, plus the read-only `knowledge_assistant`.
- **FR-045**: Required logical identities MUST be protected from user deletion but MAY evolve
  through an approved constitutional or product-specification change.
- **FR-046**: Every required logical agent MUST use the Codex-hosted runtime by default. Runtime,
  provider, model, compatible fallback chain, credential reference, model parameters, timeout,
  retry policy, system prompt, and user prompt MUST be independently configurable through the UI;
  LiteLLM MAY be selected only through an explicit per-agent or model-profile override.
- **FR-047**: System prompt resolution MUST be Agent System Prompt Override, then Orchestrator
  System Prompt, then Platform Default.
- **FR-048**: User prompt resolution MUST independently be Agent User Prompt Override, then
  Orchestrator User Prompt, then Platform Default.
- **FR-049**: An override in one prompt type MUST NOT override or alter inheritance of the other
  prompt type.
- **FR-050**: Material prompt changes MUST create versions, and each material execution MUST retain
  the resolved system and user prompt versions, selected runtime, actual model and provider,
  fallback use, and whether an alternative runtime was explicitly configured.
- **FR-051**: Matrades MUST reject activation of a required agent whose selected runtime, assigned
  model, and same-runtime fallbacks cannot meet that role's declared structured-output, tool-use,
  or context requirements. Matrades MUST NOT automatically fall back between the Codex-hosted
  runtime and LiteLLM.
- **FR-052**: Agent tool permissions MUST be configured independently of model and prompt settings;
  changing a model or prompt MUST NOT grant additional authority.
- **FR-053**: Agents MUST exchange versioned structured results containing evidence, source times,
  confidence or uncertainty, assumptions, and status.
- **FR-054**: Agents MUST NOT receive direct broker-write, hard-policy-write, or guardrail-write
  credentials. Broker writes MUST pass through the deterministic execution service, which validates
  the structured action against current account permissions, policy, risk, and kill-switch state.

#### Strategy Creation, Repository, and Validation

- **FR-055**: The Strategy Lab MUST support exactly `AI_GENERATED` and `AI_ASSISTED` creation paths
  into one canonical repository; it MUST NOT expose human-created or imported origins.
- **FR-056**: `AI_GENERATED` MUST invoke `strategy_researcher` to select the strategy family and
  produce a complete deterministic proposal without requiring a user-authored idea.
- **FR-057**: `AI_ASSISTED` MUST require a human description and invoke `strategy_assistant` to
  identify missing or ambiguous rules and expand the idea into a complete step-by-step proposal.
- **FR-058**: Each AI proposal MUST include its family, deterministic rules, step-by-step breakdown,
  evidence, and the originating logical-agent identity. Strategy research MUST be grounded in an
  immutable approved-market evidence pack containing the selected candidate and fingerprint,
  point-in-time provider history, applicable account and policy context, prior strategy and
  performance evidence, and owner-scoped contextual knowledge citations where available. The
  agent MUST generate multiple hypotheses, while a deterministic chronological holdout screen—not
  the agent—selects the proposal shown for approval. Missing, stale, or uncitable grounding MUST
  produce a safe degraded result rather than an invented strategy.
- **FR-059**: AI output MUST remain proposed and non-canonical until the user explicitly APPROVES
  it; REJECT MUST preserve the research record without creating a canonical strategy version.
- **FR-060**: Strategy history MUST retain origin, creator, AI contribution, human approval actor
  and time, lineage, and the immutable timestamped strategy-research archive path and checksum.
- **FR-061**: Draft strategies MUST be saveable and resumable; incomplete strategies MUST remain
  drafts and MUST show the rules preventing deterministic implementation.
- **FR-062**: A complete specification MUST define family, markets and instruments, regimes,
  horizon, analysis dependencies, entry, confirmation, filters, invalidation, Stop Loss, Take
  Profit, management, risk, session, and event constraints as applicable.
- **FR-063**: Strategy specification and deterministic implementation MUST remain separate; model-
  generated executable behavior MUST NOT automatically enter live use.
- **FR-064**: Every strategy origin MUST undergo canonical-rule, structural, semantic, parameter,
  and, where evidence exists, behavioral similarity analysis before a new identity is created.
- **FR-065**: Similarity outcomes MUST distinguish exact duplicate, near duplicate, variant, new
  version, and new strategy and MUST offer appropriate compare, reuse, or branch actions.
- **FR-066**: A strategy MUST support permanent identity, name, origin, creator, family, versions,
  canonical rules, lineage, supported regimes and markets, instrument profiles, validation,
  account-policy compatibility, status, health, and performance history.
- **FR-067**: Material rule or behavior changes MUST create a separately validated version; profile
  or parameter changes MAY remain attached to the same version when canonical behavior is unchanged.
- **FR-068**: All origins MUST pass the same lifecycle: DRAFT, SPECIFIED, IMPLEMENTED, BACKTESTING,
  VALIDATING, PAPER_TRADING, APPROVED, and ACTIVE, with DEGRADED, SUSPENDED, and RETIRED available
  after activation.
- **FR-069**: Validation MUST include chronological backtesting, out-of-sample testing, walk-forward
  testing, applicable stress or Monte Carlo analysis, account-rule simulation, and paper trading.
- **FR-070**: Backtesting MUST account for relevant spread, fees, commission, slippage, financing,
  funding, and contract terms and MUST prevent future information from influencing earlier decisions.
- **FR-071**: Validation results MUST include trade count, win rate, average winner and loser,
  expectancy, average R, Profit Factor, drawdown, consecutive losses, MAE, MFE, and performance by
  applicable regime, session, and instrument.
- **FR-072**: Only APPROVED or ACTIVE strategies compatible with the current account and market MAY
  produce live proposals; selection MUST rank suitability and health without favoring origin.
- **FR-073**: A regime-driven strategy switch MUST NOT itself create a trade signal; the newly
  selected strategy MUST independently detect a valid setup.
- **FR-074**: Improving an active strategy MUST create a separate draft or proposed version and MUST
  leave the active version unchanged until the replacement completes validation and promotion.

#### Knowledge and Retrieval

- **FR-075**: Matrades MUST distinguish structured application records, time-series observations,
  and semantic knowledge so that each request uses the authoritative record type for its purpose.
- **FR-076**: Authorized users and agents MAY retrieve strategy research, prop-firm documents,
  historical research, journal commentary, and research notes as contextual evidence.
- **FR-077**: Retrieved records MUST retain document identity, source or reference, source type,
  version, owner or account scope, document date, ingestion time, segment identity, and tags.
- **FR-078**: Semantic similarity MUST NOT be the sole basis for strategy duplication, performance
  calculation, policy enforcement, current market facts, or current account and risk state.
- **FR-079**: Users MUST be able to view, enable or disable, inspect, reprocess, and delete authorized
  knowledge sources and see source and retrieval health without operating storage internals.
- **FR-080**: Knowledge unavailability MUST mark dependent research DEGRADED while leaving
  deterministic account, policy, risk, and essential monitoring functions unaffected.
- **FR-108**: The `knowledge_assistant` MUST answer natural-language questions only from records
  authorized for the current user and account scope, cite the knowledge or journal segments
  supporting material factual claims, distinguish retrieved evidence from inference, and state when
  the available evidence is insufficient.
- **FR-109**: The `knowledge_assistant` MUST have no execution-service or broker-write tool, MUST NOT
  create executable trade plans, and MUST refuse requests to enter, cancel, modify, partially close,
  or fully exit a trade even when the account otherwise permits autonomous execution.
- **FR-110**: Every committed live-trade journal event MUST be queued for continuous, owner-scoped
  semantic indexing and MUST retain a stable reference to the authoritative structured journal event;
  indexing failure MUST NOT remove, alter, or delay the authoritative journal record.
- **FR-111**: The Journal agent MUST append immutable observations for material market, account,
  risk, strategy, execution, and position-state changes throughout a reconciled trade and MUST record
  observation time, evidence time, sources, trade-plan and position identities, agent/model/prompt
  identity, and whether the content is observation or inference.
- **FR-112**: When a trade reaches a terminal state, the Journal agent MUST create a consolidated
  post-trade summary covering the plan, execution, management chronology, rationale, outcome, fees,
  MAE, MFE, lessons, and cited journal-event range, then index that summary without replacing its
  underlying events.
- **FR-113**: The Knowledge Assistant MAY answer from indexed live events before trade close but
  MUST label the trade as active and the account, position, price, P&L, and risk values as historical
  observations unless they are independently refreshed from authoritative structured services.

#### Trade Construction, Reconciliation, and Monitoring

- **FR-081**: Setup detection MUST apply deterministic rules of the selected validated strategy.
- **FR-082**: Trade construction MUST deterministically calculate direction, entry or zone, Stop
  Loss, target or targets, invalidation, compliant size, risk, maximum loss, and Risk:Reward.
- **FR-083**: Every candidate MUST pass the active account's policy, effective guardrails, current
  equity and dynamic capacity, portfolio risk, and adversarial critic review before execution.
- **FR-084**: An executable trade plan MUST include trade construction, strategy and version, regime,
  evidence and invalidation, the complete FR-032 equity snapshot, policy and guardrail results,
  critic result, and concise reasons for execution or restriction.
- **FR-085**: Broker connections MUST default to read-only until the user explicitly enables
  per-account execution permissions and MUST then support authorized order entry, cancellation,
  protection changes, partial closes, full exits, and the account, equity, positions, orders,
  history, P&L, and symbol details required for reconciliation.
- **FR-086**: Matrades MUST support a health-reporting MT5 Bridge for Windows, macOS/Wine, or
  hosted environments without making MT5 the only supported broker path.
- **FR-087**: Reconciliation MUST match detected positions using instrument, direction, time, entry
  proximity, size, and pending executable Trade Plans; an ambiguous match MUST be marked BLOCKED and
  MUST NOT receive autonomous management actions until authoritative evidence resolves it uniquely.
- **FR-088**: Once reconciled, actual broker entry, size, Stop Loss, Take Profit, fees, and P&L MUST
  replace proposed values as the authority for monitoring and journaling.
- **FR-089**: Monitoring MUST assess the actual position, market evidence, strategy invalidation,
  events, applicable policy, account state, P&L, and remaining risk and MAY output HOLD, MOVE SL,
  PARTIAL TP, EARLY EXIT, or FULL EXIT.
- **FR-090**: A broker or bridge disconnect MUST mark broker state stale, block confirmation-
  dependent actions, and continue safe monitoring from remaining authoritative sources where possible.
- **FR-114**: Every active-position view MUST display the complete versioned Trade Plan alongside an
  embedded interactive chart, including strategy and version, direction, planned and actual entry,
  size, invalidation, Stop Loss, Take Profit targets, risk, maximum loss, Risk:Reward, management
  rules, current execution state, and concise rationale.
- **FR-115**: Embedded charts MUST support live and historical authoritative candles or price updates,
  pan, zoom, configured timeframes, and supported indicators, with overlays for planned and actual
  entry, fills, Stop Loss, Take Profit, partial and full exits, live journal events, and automated
  management actions.
- **FR-116**: Embedded charts MUST be operationally read-only: chart interactions MUST NOT create a
  Trade Plan, execution-service request, or broker command and the chart component MUST receive no
  broker-write credential or tool.
- **FR-117**: Every chart MUST show normalized instrument identity, asset class, instrument type,
  provider, source timestamp, freshness or delay state, timeframe, and broker-symbol mapping; stale,
  disconnected, or mismatched chart data MUST be visibly degraded and MUST NOT be presented as the
  authoritative current broker position.

#### Journal, Performance, Operations, and UI

- **FR-091**: The journal MUST retain research selections, analysis, strategy and
  policy versions, proposed and actual trades, account-risk snapshots, agent/model/prompt identities,
  automated decisions, execution requests, broker changes, timestamps, fees, exit reason, MAE, MFE,
  and outcome.
- **FR-092**: Performance MUST be calculated from structured results and be attributable by strategy
  and version, instrument, market category, regime, session, account, prop firm, and relevant agent
  configuration where data permits.
- **FR-118**: Every performance observation MUST be classified as `BACKTEST`, `PAPER`, or `LIVE`;
  headline win rate, P&L, drawdown, profitability, loss, and edge metrics MUST be calculated separately
  for each evidence class and MUST NOT blend simulated and live results.
- **FR-119**: Operational performance views MUST default to `LIVE` and MUST support side-by-side
  comparison of evidence classes plus filters for period, account, prop firm, strategy and version,
  asset class, instrument type, instrument, direction, regime, session, and exit reason.
- **FR-120**: Each evidence-class metric set MUST include completed, winning, losing, and breakeven
  trades; win and loss rate; gross and net P&L; return; average and total monetary loss; average winner
  and loser; payoff ratio; expectancy in money and R after costs; Profit Factor; maximum and current
  drawdown; recovery factor; consecutive wins and losses; MAE; MFE; holding time; fees; financing or
  funding; slippage where observable; and risk-adjusted return where the sample supports it.
- **FR-121**: Matrades MUST present trading edge as after-cost expectancy with its evidence class,
  formula, sample size, observation period, uncertainty or confidence interval, and status of POSITIVE,
  INCONCLUSIVE, or NEGATIVE; AI narrative MUST NOT calculate or override the deterministic metric.
- **FR-122**: Unrealized P&L and risk for open positions MUST be displayed separately from realized
  performance and MUST NOT alter completed-trade win rate or expectancy.
- **FR-123**: Every displayed aggregate MUST drill down to its contributing structured trades and
  disclose exclusions, missing values, source freshness, currency conversion, and calculation version.
- **FR-093**: Strategy degradation MAY create research or suspension actions but MUST NOT directly
  mutate an active strategy.
- **FR-094**: The UI MUST separate operational work from configuration and provide markets,
  research, trade desk, open trades with embedded charts and adjacent trade plans, automation controls,
  strategies, validation, journal, performance, accounts, rules, connections, risk, agents, knowledge,
  notifications, and security views.
- **FR-095**: A centralized automation operations view MUST group active trade plans, broker orders,
  position-management actions, blocked actions, and kill-switch state by account and urgency.
- **FR-096**: The UI MUST expose RESEARCHING, WAITING, ACTION REQUIRED, ACTIVE, BLOCKED, DEGRADED,
  and OFFLINE states without requiring the user to inspect agent logs.
- **FR-097**: Health views MUST cover required agents, models, data and calendar sources, broker and
  bridge connections, knowledge retrieval, and notification channels, including status, freshness,
  last success, and error state.
- **FR-098**: Notifications MUST support in-product delivery and MAY support browser, email,
  Telegram, and additional replaceable channels for executions, safety warnings, critical events,
  disconnections, failures, and strategy degradation.
- **FR-124**: A confirmed broker acceptance or fill for a new entry MUST generate one deduplicated
  trade-entry notification through every enabled channel. The notification MUST distinguish pending,
  partial, and complete fills and include account, instrument, side, quantity, broker price or order
  level, Stop Loss and Take Profit, strategy and version, execution time, and a link to the active
  Trade Plan; a proposed or submitted order without broker confirmation MUST NOT be reported as entered.
- **FR-099**: Every material trading decision MUST be reconstructable from data sources and times,
  market fingerprint, strategy and version, policy and guardrails, equity and risk snapshot, agent
  configuration, actual model and fallback, prompt versions, tools used, human actions, and broker
  outcome.
- **FR-100**: User-facing trade, block, and strategy-selection decisions MUST provide concise reasons,
  evidence, restrictions, and invalidation without exposing private model reasoning.

#### Cross-Cutting V1 Commitments

- **FR-101**: Users MUST be able to configure and test a LiteLLM-compatible gateway as an explicit
  alternative runtime, view its health, and synchronize its available models into the Matrades
  model catalog. Configuring or connecting the gateway MUST NOT reassign any agent from the default
  Codex-hosted runtime.
- **FR-102**: The model catalog MUST represent models independently from agents and MUST support
  reusable profiles containing a runtime type, primary model, same-runtime fallback chain,
  parameters, operating limits, and required capabilities. A profile that selects LiteLLM MUST be
  explicitly assigned before use.
- **FR-103**: Strategy classification MUST separately represent strategy family, strategy, reusable
  pattern, market regime, analysis dependency, trading horizon, signal, and trade.
- **FR-104**: The initial strategy taxonomy MUST accommodate trend, momentum, breakout, reversal,
  mean-reversion, liquidity, support/resistance, supply/demand, event, macro, carry, volatility,
  statistical, relative-value, arbitrage, market-making, order-flow, positioning, seasonality,
  intermarket, and funding/basis families, plus reusable structure and liquidity patterns.
- **FR-105**: Each trading account MUST have independently configurable permissions for new entry,
  order cancellation, Stop Loss changes, Take Profit changes, partial closes, and full exits; a
  disabled permission MUST hard-block that broker write without disabling safe read-only monitoring.
- **FR-106**: Each account and the platform as a whole MUST provide an emergency kill switch that
  immediately blocks new entries and discretionary broker writes, remains effective across service
  restarts, is visible in operational views, and does not cancel broker-hosted protective orders.
- **FR-107**: Every broker write MUST use an idempotency key or equivalent command identity, record
  its initiating trade plan and deterministic checks, and reconcile uncertain broker outcomes before
  any retry to prevent duplicate execution.

### Key Entities *(include if feature involves data)*

- **User**: Authenticated owner of configuration, accounts, strategies, approvals, and knowledge;
  includes verification, MFA, recovery, session, and authorization state.
- **Credential Reference**: Masked, access-controlled reference to a provider secret; includes owner,
  provider purpose, status, replacement history, test state, and audit metadata, never the displayed
  secret value.
- **Trading Account**: Personal or prop-firm account context; includes currency, nominal size,
  current broker connection, execution mode, ruleset, guardrail profile, status, and snapshots.
- **Account Equity Snapshot**: Time-bound authoritative account state containing starting balance,
  balance, equity, floating and realized daily P&L, drawdown values, limits, positions, reserved risk,
  exposure, remaining capacities, freshness, source, and account identity.
- **Prop-Firm Ruleset**: Versioned rules for one firm/program/account context with source, effective
  and verification dates, verification state, enforcement levels, and historical applicability.
- **Guardrail Profile**: User-defined internal risk and operating limits scoped globally or to an
  account or strategy.
- **Risk Capacity Result**: Candidate-specific PASS, REDUCE SIZE, or HARD BLOCK decision with
  limiting constraints, compliant size if any, projected worst-case loss, post-trade exposure,
  additional-trade capacity, and snapshot reference.
- **Market Instrument**: Provider-neutral tradeable instrument with asset class, instrument type
  (spot, CFD, or futures), normalized symbol, provider mappings, contract or venue properties,
  and availability state.
- **Market Snapshot and Fingerprint**: Time-stamped authoritative observations and derived regime,
  structure, liquidity, volatility, event, sentiment, and intermarket state used by a decision.
- **Agent Definition**: Stable logical role and ID with required capabilities and allowed tools;
  defaults to the Codex-hosted runtime and remains separate from its independently versioned,
  explicitly selected runtime/model profile and prompt configuration.
- **Knowledge Answer**: Read-only response containing the question, authorized source segments,
  citations, evidence-versus-inference labels, insufficiency state, agent/model/prompt identity, and
  timestamp; it has no executable trading representation.
- **Live Journal Observation**: Immutable, trade-scoped record created during monitoring with event
  and evidence timestamps, cited sources, structured state references, observation-versus-inference
  label, and indexing status.
- **Prompt Version**: Versioned system or user prompt with scope, inheritance mode, author, and time;
  the two prompt types resolve independently.
- **Strategy**: Permanent canonical identity with origin, creator, family, rules, lineage, supported
  contexts, profiles, status, health, and versions.
- **Strategy Version**: Immutable material rule set with provenance, implementation and validation
  state, evidence, compatibility, performance, and lifecycle status.
- **Knowledge Record**: Authorized contextual document or segment with source provenance, version,
  owner/account scope, date, ingestion state, and tags; never authoritative for current risk facts.
- **Trade Plan**: Executable, versioned instruction linking market evidence, selected strategy,
  construction, equity snapshot, policy, guardrail, risk and critic results, account permissions,
  deterministic authorization, and execution state.
- **Broker Position**: Actual connected-account state used after reconciliation, including entry,
  size, protection levels, fees, P&L, status, and broker timestamps.
- **Chart View State**: Non-executable presentation state containing normalized instrument mapping,
  provider and freshness, timeframe, indicators, visible range, Trade Plan reference, broker-position
  reference, and overlay event references; it carries no broker command semantics.
- **Execution Permission Profile**: Account-scoped switches for entry, cancellation, protection
  changes, partial closes, and full exits, including kill-switch state, actor, version, and audit time.
- **Journal Event**: Immutable chronological evidence of research, configuration, decisions,
  execution reconciliation, monitoring, changes, and outcomes.
- **Performance Record**: Structured metric set tied to account, strategy version, instrument,
  regime, session, period, evidence class (`BACKTEST`, `PAPER`, or `LIVE`), contributing-trade
  population, calculation version, costs, exclusions, sample sufficiency, and uncertainty.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In controlled acceptance testing, 100% of candidate trades without a current,
  account-matched equity snapshot are prevented from reaching broker execution.
- **SC-002**: Across all tested boundary cases, 100% of candidates whose worst-case loss breaches
  an applicable hard rule are blocked, and the user sees the limiting value and source.
- **SC-003**: In lifecycle acceptance testing, 100% of authorized entry, cancellation, Stop Loss,
  Take Profit, partial-close, and full-exit actions execute without HIL approval, while 100% of
  disabled or hard-blocked actions produce no broker write.
- **SC-004**: In a test set containing independent and correlated positions, every displayed
  additional-trade capacity matches the effective risk, drawdown, portfolio, correlation, category,
  and concurrent-position constraints.
- **SC-005**: 100% of executable trade plans show all required construction and equity-snapshot
  fields, their freshness, and a PASS or REDUCE SIZE result; blocked candidates show equivalent
  evidence with no broker submission.
- **SC-006**: 100% of AI-assisted and AI-generated strategies are prevented from
  live eligibility until the same configured validation and paper-trading gates pass.
- **SC-007**: At least 90% of representative first-time users can turn a partial strategy idea into
  a reviewable deterministic AI-assisted proposal and approve or reject it without assistance.
- **SC-008**: In duplicate test cases, 100% of exact canonical duplicates are detected before a new
  strategy identity is committed, and at least 90% of reviewed near-duplicate cases are surfaced.
- **SC-009**: In acceptance testing, 100% of required logical agents resolve to the Codex-hosted
  runtime without an override; an operator can explicitly assign LiteLLM per agent or model profile,
  independently change model, system prompt, and user prompt, and verify that no execution crosses
  runtimes automatically or changes tool rights.
- **SC-010**: 100% of configuration views and audit exports show saved secrets only in masked form;
  no raw secret appears in model prompts or operational logs during security testing.
- **SC-011**: When semantic knowledge is unavailable, 100% of tested risk, policy, equity, and
  essential live-monitoring decisions either continue from healthy authoritative data or fail safe
  without using fabricated retrieval results.
- **SC-012**: At least 95% of daily market-research runs present ranked results or an explicit safe-
  failure status within 10 minutes after all required source data becomes available.
- **SC-013**: At least 95% of complete candidate evaluations present a decision or a clear blocked/
  degraded status within 5 seconds after all authoritative inputs are available.
- **SC-014**: Auditors can reconstruct 100% of sampled material trade decisions from recorded data,
  versions, resolved agent configuration, human actions, and broker outcomes without relying on
  private model reasoning.
- **SC-015**: At least 90% of representative users can identify whether the system is waiting for
  them, actively monitoring, blocked, degraded, or offline within 10 seconds of opening the relevant
  operational view.
- **SC-016**: In adversarial acceptance testing, 100% of conversational requests to enter, cancel,
  modify, partially close, or fully exit a trade through the Knowledge Assistant create no trade
  plan, execution-service request, or broker command.
- **SC-017**: In a representative grounded-answer test set, 100% of the Knowledge Assistant's
  material factual claims include an authorized journal or knowledge citation or are explicitly
  labeled as unsupported or inferred.
- **SC-018**: At least 99% of committed live journal events become searchable within 60 seconds when
  the knowledge index is healthy, and 100% remain present in the authoritative journal when indexing
  is unavailable or fails.
- **SC-019**: In lifecycle acceptance testing, 100% of terminal trades produce one consolidated
  post-trade summary linked to the complete immutable event range and the corresponding trade,
  position, account, strategy version, and execution records.
- **SC-020**: In active-trade UI acceptance testing, 100% of sampled positions display their current
  Trade Plan beside a chart whose entry, fill, Stop Loss, Take Profit, exit, journal, and automated-
  action overlays resolve to the same account, instrument mapping, position, and source timestamps.
- **SC-021**: In interaction and security testing, 100% of chart pan, zoom, timeframe, and indicator
  actions create no Trade Plan, execution-service request, broker command, or broker credential access.
- **SC-022**: In analytics acceptance testing, 100% of headline metrics are traceable to exactly one
  evidence class and the live default never includes a backtest or paper-trading observation.
- **SC-023**: For a deterministic analytics fixture, 100% of displayed win rate, net P&L, total loss,
  expectancy, Profit Factor, drawdown, and edge status match the versioned calculation definitions and
  drill down to the exact contributing trades.
- **SC-024**: In broker-notification acceptance testing, 100% of confirmed new entries emit exactly
  one notification per enabled channel, including partial-fill updates without duplicate entry alerts,
  and 0% of unconfirmed submissions are described as entered trades.

## Assumptions

- V1 serves an individual authenticated trader; multi-user teams and shared strategy workspaces are
  outside this feature unless explicit authorized sharing is added later.
- Live trade entry and position management are automated only for explicitly enabled per-account
  permissions; broker connections remain read-only until those permissions are activated.
- The default research universe is one instrument per enabled asset-class and instrument-type
  combination. Spot means cash or underlying ownership, CFD means derivative exposure, and futures
  mean contract exposure. Each combination is eligible only when its market semantics and
  authoritative provider or broker mapping are configured; configuration or a later specification
  may broaden the universe without weakening deterministic policy or risk constraints.
- Users supply and verify their applicable prop-firm terms. Matrades may assist extraction but does
  not guarantee that unverified source text is complete or legally authoritative.
- Risk policies define reset boundaries, currencies, conversion rules, drawdown bases, and whether
  unrealized profit can contribute to capacity; absent an explicit rule, the conservative treatment
  applies.
- Each open position has enough current broker information to calculate worst-case loss. If it does
  not, new trade eligibility fails safe until risk can be bounded.
- Providers named for V1 are initial product integrations rather than permanent architectural
  dependencies and may be replaced through equivalent configured sources.
- Statistical performance uses structured trades and backtests; retrieved narrative may explain but
  never calculate authoritative metrics.
- Required logical agent identities are the minimum initial registry and can change only through an
  approved constitutional or product-specification update.
- The Codex-hosted runtime is the default execution environment for all required agents. If it is
  unavailable, an agent without an explicit LiteLLM assignment fails safe rather than switching
  runtimes automatically.
- Notification channels other than in-product delivery depend on user-configured external services.
- Data retention, deletion, and export follow applicable security and financial-record obligations;
  exact retention schedules will be established during planning without weakening audit history.
