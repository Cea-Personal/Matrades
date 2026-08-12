# Feature Specification: TraderX Core Platform

**Feature Branch**: `master`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Create the TraderX product specification from the attached
TraderX Speckit Specify v1.0.0 document."

## Clarifications

### Session 2026-08-12

- Q: How should the first TraderX owner create their account on a new installation? → A: One-time self-service owner setup in the UI, followed by mandatory TOTP enrollment.
- Q: How should a user regain access after losing their TOTP authenticator? → A: One-time recovery codes, plus owner/admin-assisted TOTP reset if all codes are lost.
- Q: Should authentication use separate, deep-linkable pages for sign-in, first-owner setup, MFA, password reset, and recovery? → A: Separate routes for each authentication and recovery step.
- Q: After a user follows a password-reset link, what proof should TraderX require before issuing a new session? → A: Require current TOTP or an unused recovery code after the verified reset link.
- Q: What session lifetime should the authentication UI enforce before requiring the user to sign in again? → A: Expire after 30 idle minutes or 12 total hours, whichever comes first.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish a Safe Trading Account (Priority: P1)

As an owner, I authenticate, connect one primary trading account, configure its prop-firm rules,
and set stricter internal risk limits so every later decision uses the correct shared-equity
constraints.

**Why this priority**: No research result or recommendation is safe without trusted account data,
access control, and explicit loss boundaries.

**Independent Test**: Starting from a new installation, an owner can sign in, enable MFA, connect
an account, configure external and internal risk limits, and see the resulting risk state and
position capacity without using technical administration tools.

**Acceptance Scenarios**:

1. **Given** an unauthenticated visitor, **When** they request an operational screen, **Then** they
   are required to authenticate before any account or trading information is shown.
2. **Given** an authenticated owner, **When** they configure an account and valid prop-firm and
   internal risk rules, **Then** the Command Center shows current equity, loss margins, risk state,
   open risk, and position capacity derived from those rules.
3. **Given** an internal limit stricter than the corresponding prop-firm limit, **When** current
   losses reach the internal boundary, **Then** TraderX blocks new recommendations even though the
   external boundary has not been reached.
4. **Given** a new installation with no owner, **When** a visitor completes the one-time initial
   owner setup with an email and password, **Then** TraderX creates exactly one `OWNER`, requires
   TOTP enrollment, and exposes no operational information until MFA is completed.
5. **Given** a user has lost their authenticator, **When** they present an unused recovery code,
   **Then** TraderX permits TOTP re-enrollment, revokes existing sessions, and records the recovery
   event; if no recovery code remains, only an authorized `OWNER` or `ADMIN` may initiate an
   audited reset.
6. **Given** a user enters or resumes an authentication workflow, **When** they navigate directly
   to its sign-in, initial-owner setup, MFA enrollment, MFA verification, password-reset, or MFA
   recovery screen, **Then** TraderX displays only the valid step and never exposes operational
   content before authentication is complete.
7. **Given** a user follows a valid password-reset link, **When** they set a new password, **Then**
   TraderX requires current TOTP or an unused recovery code before issuing a new session and
   revokes existing sessions after the reset.
8. **Given** an authenticated user is inactive for 30 minutes or their session reaches 12 hours,
   **When** they request an operational screen or action, **Then** TraderX ends the session,
   returns them to sign-in, and does not complete the pending action.

---

### User Story 2 - Select Three Eligible Active Markets (Priority: P1)

As an owner, I research broker-supported Commodity, Forex, and Cryptocurrency candidates, compare
their volatility, liquidity, execution, data quality, and account compatibility, and approve one
eligible instrument in each category.

**Why this priority**: The active universe determines where TraderX may search for live
opportunities and must exclude attractive but impractical markets.

**Independent Test**: With candidate and account data available, the user can run market-universe
research, inspect eligibility decisions and suitability ranks, approve exactly one instrument per
category, and later replace one only through explicit confirmation.

**Acceptance Scenarios**:

1. **Given** candidates with different volatility and liquidity profiles, **When** research
   completes, **Then** only instruments that pass every required eligibility gate participate in
   final ranking.
2. **Given** a highly volatile but illiquid instrument, **When** it fails the liquidity gate,
   **Then** it cannot be selected regardless of raw volatility.
3. **Given** no approved active instrument in a category, **When** the user reviews the completed
   ranking, **Then** they can approve one eligible candidate or leave the category inactive; the
   system never silently approves it.
4. **Given** three approved active instruments, **When** a new candidate ranks higher, **Then** the
   current instrument remains active until the user approves a replacement.

---

### User Story 3 - Build and Validate a Strategy (Priority: P1)

As a trader, I create or discover an explicit strategy, version it, backtest it realistically,
validate it on unseen and changing data, assess robustness and shared-account risk, and determine
whether it qualifies for paper trading.

**Why this priority**: TraderX cannot generate trustworthy live recommendations without a
reproducible evidence chain and enforced lifecycle.

**Independent Test**: Using prepared historical data, the trader can define a strategy without
writing code, run each required validation stage, inspect all required evidence, and observe that
an invalid transition is rejected.

**Acceptance Scenarios**:

1. **Given** a draft strategy with explicit entry, exit, risk, and invalidation rules, **When** the
   user starts validation, **Then** results remain tied to that immutable strategy version and the
   exact research assumptions.
2. **Given** a strategy that performs well only on development data, **When** unseen-data or
   robustness validation fails, **Then** it cannot enter paper trading.
3. **Given** a validated strategy is edited, **When** the change is saved, **Then** a new immutable
   version is created and previous evidence remains attached to the old version.
4. **Given** a strategy that is profitable alone but breaches shared-account risk in portfolio
   testing, **When** validation concludes, **Then** it is rejected or returned for research.

---

### User Story 4 - Paper Trade and Approve a Strategy (Priority: P1)

As an authorized trader, I paper trade a historically validated strategy on current data, compare
observed performance with expectations, and explicitly approve, reject, or return it to research.

**Why this priority**: Current forward evidence and human approval are mandatory boundaries before
live recommendation eligibility.

**Independent Test**: With a historically qualified strategy, simulated execution can run until
configured evidence requirements are met, after which only an authorized user can promote it.

**Acceptance Scenarios**:

1. **Given** a historically qualified strategy, **When** paper trading starts, **Then** simulated
   trades use current data, the production rules, current risk limits, and realistic costs.
2. **Given** paper results diverge materially from historical expectations, **When** results are
   evaluated, **Then** the strategy enters review, research, or failed status rather than being
   promoted automatically.
3. **Given** all paper requirements are met, **When** processing completes, **Then** the strategy
   enters `AWAITING_APPROVAL` and produces no actionable live recommendation until an authorized
   user approves it.

---

### User Story 5 - Receive a Risk-Approved Recommendation (Priority: P1)

As a trader, I compare live opportunities across the three active markets and receive a complete,
expiring recommendation only when a live-approved strategy, portfolio capacity, and the Risk
Manager all permit it.

**Why this priority**: This is the principal decision-support outcome while preserving the
constitutional boundary against automatic live execution.

**Independent Test**: With prepared active markets, strategies, account state, and market data,
TraderX ranks candidates, calculates size, explains pass or block decisions, and never exceeds
the allowed shared-account capacity.

**Acceptance Scenarios**:

1. **Given** multiple valid opportunities and sufficient capacity, **When** they are evaluated,
   **Then** the trader sees a ranked comparison and a complete recommendation for each passing
   candidate.
2. **Given** one open position, **When** a correlated second candidate appears, **Then** it is
   approved, reduced, or blocked using combined risk and remaining loss margin.
3. **Given** two open positions, **When** any third candidate appears, **Then** it is blocked with
   the maximum-position reason regardless of score.
4. **Given** a valid high-scoring setup but missing critical account or market data, **When** the
   Risk Manager evaluates it, **Then** no new live recommendation is issued.
5. **Given** a previously actionable recommendation, **When** its time, price, candle, structure,
   or strategy validity expires, **Then** it is visibly non-actionable.

---

### User Story 6 - Manually Execute and Monitor a Trade (Priority: P1)

As a trader, I place a recommended order manually at my broker, have TraderX detect and classify
the position, and monitor current evidence against the frozen original thesis while account risk
updates continuously.

**Why this priority**: TraderX must support the live trade after recommendation without crossing
the manual-execution boundary.

**Independent Test**: A prepared broker position can be detected, linked or classified as
discretionary, reflected in risk and capacity, monitored against an immutable thesis, and closed
without TraderX submitting a real-money order.

**Acceptance Scenarios**:

1. **Given** an actionable recommendation, **When** the trader manually opens the matching broker
   position, **Then** TraderX links it to the recommendation and freezes the original thesis.
2. **Given** a broker position with no matching recommendation, **When** it is detected, **Then** it
   is classified as discretionary, affects shared risk immediately, and can be corrected by the
   user.
3. **Given** an open recommended trade, **When** evidence changes, **Then** TraderX reports thesis
   health and relevant alerts without rewriting the original thesis or executing an order.

---

### User Story 7 - Journal Outcomes and Learn (Priority: P2)

As a trader, I review an automatically populated trade journal, add behavioral context and
screenshots, analyze normalized and financial results, and turn findings into research hypotheses.

**Why this priority**: Durable learning improves future research while preserving historical
evidence.

**Independent Test**: Closed recommended, discretionary, and paper trades produce journal records
that accept manual annotations, support performance breakdowns, and generate proposals without
changing a strategy automatically.

**Acceptance Scenarios**:

1. **Given** a trade closes, **When** its final broker data is available, **Then** the journal
   records its execution, strategy, risk context, thesis, monitoring events, profit/loss, and R.
2. **Given** journal history across strategies and regimes, **When** the user analyzes it, **Then**
   they can compare performance by instrument, strategy version, time, direction, risk state,
   regime, and behavior.
3. **Given** journal analysis finds a repeatable pattern, **When** it creates a hypothesis, **Then**
   the hypothesis enters research and does not silently modify a live strategy.

---

### User Story 8 - Replace and Reactivate Markets Without Losing Knowledge (Priority: P2)

As an owner, I replace an active market while preserving its history and later reactivate it by
reusing current evidence and refreshing or revalidating only what is stale.

**Why this priority**: Market conditions change, but accumulated research and audit history remain
valuable and must never be discarded.

**Independent Test**: An active instrument can be deactivated and replaced; all knowledge remains
available; reactivation identifies data gaps and evidence staleness before any live use.

**Acceptance Scenarios**:

1. **Given** an active instrument with research, strategies, and trade history, **When** it is
   replaced, **Then** all associated knowledge remains available in the Instrument Library.
2. **Given** a formerly active instrument, **When** reactivation begins, **Then** TraderX identifies
   reusable knowledge, missing data, and required revalidation.
3. **Given** a previously live but now stale strategy, **When** its instrument is reactivated,
   **Then** the strategy cannot generate live recommendations until required validation and human
   approval are current.

---

### User Story 9 - Operate and Audit TraderX from the UI (Priority: P2)

As an authorized user, I manage integrations, background work, alerts, strategy health, system
health, and audit history through the web interface while sensitive values remain protected.

**Why this priority**: Safe routine operation must not require shell access, direct data access, or
configuration-file changes.

**Independent Test**: An authorized user can connect, test, disable, reconnect, and rotate an
integration; manage a long-running job; configure notifications; and review audit records entirely
through authenticated screens.

**Acceptance Scenarios**:

1. **Given** valid credentials for an approved external service, **When** the owner connects and
   tests it, **Then** status and freshness are visible while the secret remains masked and absent
   from ordinary logs.
2. **Given** a long-running research or validation job, **When** the user views system work, **Then**
   they see its state and may perform only the valid actions for that state.
3. **Given** a material risk, strategy, market, integration, or security change, **When** it is
   completed, **Then** the audit history records actor, action, time, reason, and previous/new
   values where applicable.

### Edge Cases

- Account equity is unknown, contradictory, delayed, or changes while a recommendation is being
  evaluated.
- Daily and overall drawdown use different reset rules, time zones, or floating-loss treatments.
- A broker reports a partial fill, multiple fills, an externally modified stop, or a position not
  created from a TraderX recommendation.
- A second opportunity is individually valid but duplicates currency, macro, regime, or strategy
  exposure already held.
- Market data is fresh but contract specifications, tick value, or minimum volume are missing.
- The most volatile candidate has unreliable history, a wide spread, shallow depth, excessive
  slippage, unacceptable gaps, or a prop-firm restriction.
- Two candidates have equal suitability scores or insufficient evidence to distinguish them.
- Market-universe research completes with no eligible instrument in one category.
- A market ranking changes while the user is reviewing a replacement.
- An instrument is archived and later returns under a different broker symbol.
- A strategy is changed while a backtest, paper run, or approval review is in progress.
- Historical validation has too few trades or insufficient market regimes for a reliable result.
- A paper strategy meets its calendar duration but not its evidence threshold, or vice versa.
- A live-approved strategy becomes stale, unhealthy, or suspended while one of its positions is
  still open.
- A recommendation expires at the same moment a manually opened broker position is detected.
- A circuit breaker activates while background research and paper trading are running.
- An integration fails during a long-running job and later recovers.
- The same trade update arrives more than once or arrives out of order.
- An unauthorized role attempts to approve a strategy, relax risk, replace a market, rotate a
  secret, or override a circuit breaker.
- Two visitors attempt initial owner setup at the same time, or a visitor attempts it after an
  owner has already been created.
- A user loses their TOTP device, repeats a recovery code, or has no recovery codes available.
- A password-reset link is expired, already used, or followed without a valid TOTP code or recovery
  code.
- A session expires while a user is viewing or editing a risk-sensitive workflow.

## Requirements *(mandatory)*

### Functional Requirements

#### Identity and Authorization

- **FR-001**: TraderX MUST require authentication before exposing any operational screen or data.
- **FR-002**: On a new installation with no existing owner, TraderX MUST offer a one-time,
  self-service initial `OWNER` setup in the web UI using email and password. It MUST atomically
  create no more than one initial owner, require TOTP enrollment before operational access, and
  make the setup unavailable once an owner exists. Users MUST be able to sign in with email and
  password, sign out, and initiate a password reset. A verified password-reset link MUST require
  current TOTP or an unused recovery code before TraderX issues a session, and a completed reset
  MUST revoke existing sessions.
- **FR-003**: TraderX MUST securely manage active sessions and allow authorized session revocation.
  Sessions MUST expire after 30 minutes of inactivity or 12 hours from issuance, whichever comes
  first; after expiry, TraderX MUST require sign-in before showing operational data or completing
  any action.
- **FR-004**: TraderX MUST support TOTP multi-factor authentication, and sensitive or
  risk-increasing actions MUST be eligible for reauthentication or MFA confirmation. TOTP
  enrollment MUST issue one-time recovery codes; recovery-code use and any `OWNER` or `ADMIN`
  assisted TOTP reset MUST revoke active sessions and create an audit event.
- **FR-005**: TraderX MUST support `OWNER`, `ADMIN`, and `VIEWER` roles.
- **FR-006**: Only authorized roles MUST be able to manage users, accounts, integrations, secrets,
  risk and prop-firm rules, active markets, strategy approvals, suspensions, retirement, and
  safety controls. TraderX MUST provide separate, deep-linkable web screens for sign-in, one-time
  initial-owner setup, MFA enrollment, MFA verification, password reset, and MFA recovery. Each
  screen MUST show only the controls and guidance valid for its current authentication step and
  MUST NOT expose operational content before an MFA-backed session exists.

#### Command Center, Accounts, and Risk Configuration

- **FR-007**: TraderX MUST provide a default Command Center after login showing balance, equity,
  realized and floating profit/loss, daily profit/loss, drawdown, remaining daily and overall loss
  margins, open and available risk, risk state, positions, capacity, active markets, opportunity
  rankings, critical alerts, and integration health.
- **FR-008**: Authorized users MUST be able to configure one primary live trading account in V1,
  including its identity, currency, starting balance, broker relationship, and prop-firm profile.
- **FR-009**: Authorized users MUST be able to configure prop-firm starting balance, daily and
  maximum loss limits, static or trailing drawdown, floating-loss treatment, reset time and time
  zone, consistency rules, news and weekend restrictions, instrument restrictions, and other
  account-specific constraints.
- **FR-010**: Authorized users MUST be able to configure internal per-trade and portfolio risk,
  daily loss, maximum drawdown, prop safety buffer, position limit up to two, correlation,
  consecutive-loss controls, minimum reward-to-risk, profit protection, and risk-state thresholds.
- **FR-011**: TraderX MUST apply the stricter effective rule whenever an internal and external rule
  constrain the same decision.
- **FR-012**: TraderX MUST support `NORMAL`, `CAUTION`, `DEFENSIVE`, and `LOCKDOWN` states and derive
  allowed position capacity, new-trade risk, minimum opportunity quality, permission to trade, and
  alert severity from the current state.
- **FR-013**: All instruments and positions in one account MUST share the same equity, loss limits,
  and available risk budget.
- **FR-014**: Accumulated losses MUST NOT increase allowed risk and MUST be able to reduce capacity
  from two positions to one or zero.

#### Market Universe and Instrument Knowledge

- **FR-015**: TraderX MUST maintain no more than one active Commodity, one active Forex pair, and
  one active Cryptocurrency pair.
- **FR-016**: Active instrument identifiers MUST be selected from research and MUST NOT be
  permanently hardcoded.
- **FR-017**: For each category, TraderX MUST discover candidates supported by the configured
  broker and approved data sources.
- **FR-018**: Before volatility ranking, TraderX MUST evaluate each candidate for historical and
  live data availability, freshness and quality, liquidity, volume, spread, depth where available,
  expected slippage, execution quality, contract specifications, tick size and value, minimum
  volume and step, gap and trading-hours risk, broker support, position-sizing feasibility, and
  prop-firm eligibility.
- **FR-019**: A candidate failing any mandatory eligibility gate MUST be excluded from final
  volatility and suitability ranking, with the failed reasons preserved and displayed.
- **FR-020**: TraderX MUST evaluate volatility over multiple short-, medium-, and long-term windows
  using multiple appropriate measures rather than a single session or indicator.
- **FR-021**: TraderX MUST evaluate liquidity and execution using the best reliable measures
  available for each asset class.
- **FR-022**: TraderX MUST calculate a composite Market Suitability result that balances volatility
  opportunity, liquidity, execution, data quality, strategy opportunity, trading costs, gap risk,
  and prop-firm risk.
- **FR-023**: Market Suitability methods, inputs, weights, and versions MUST be reproducible,
  explainable, and auditable; authorized users MUST be able to configure permitted weights without
  removing mandatory eligibility gates.
- **FR-024**: The market research report MUST show the evaluated universe, exclusions, candidate
  ranks, supporting measures, data range and freshness, methodology version, recommendation, and
  rationale.
- **FR-025**: Initial activation and every replacement MUST require explicit human approval; a rank
  change MUST NOT silently alter the active universe.
- **FR-026**: Inactive instruments MUST remain available for research, backtesting, synchronization,
  and strategy development but MUST NOT participate in live opportunity ranking.
- **FR-027**: TraderX MUST maintain an Instrument Library with identity, asset class, broker symbol,
  active status, data status and freshness, research and strategy counts, test and trading counts,
  and last-active date.
- **FR-028**: Deactivation, replacement, and archival MUST preserve all market data, research,
  experiments, strategy versions, validation, simulations, paper/live trades, journals, risk and
  execution statistics, selection reports, and observations.
- **FR-029**: Reactivation MUST locate prior knowledge, identify missing or stale data, refresh only
  required gaps where possible, assess strategy evidence staleness, and require current validation
  and human approval before live recommendations resume.

#### Research and Strategy Lifecycle

- **FR-030**: TraderX MUST provide a Strategy Lab through the authenticated UI for research,
  experiments, visual strategy definition, versions, backtests, validation, walk-forward analysis,
  robustness analysis, portfolio tests, paper trading, approvals, health, suspension, and
  retirement.
- **FR-031**: Users MUST be able to create research jobs by selecting an instrument, objective,
  historical period, strategy type, evidence thresholds, sessions, indicators, and regimes without
  writing code.
- **FR-032**: Research work MUST remain associated permanently with the instrument and MUST record
  data source and range, parameters, assumptions, transaction costs, strategy and engine versions,
  risk profile, objective, timestamps, and random seed where relevant.
- **FR-033**: TraderX MAY generate strategy hypotheses from patterns, regimes, sessions, volatility,
  structure, strategy failures, or journal findings, but MUST keep them experimental until the
  required lifecycle is completed.
- **FR-034**: Users MUST be able to define an explicit strategy's instrument, direction, regime,
  timeframes, entry and confirmation rules, session and event filters, volatility filters, stop,
  targets, trailing behavior, invalidation, expiration, and risk constraints without coding.
- **FR-035**: The same deterministic strategy definition MUST govern historical testing, paper
  trading, and live signal generation for a given version.
- **FR-036**: Every material strategy change MUST create an immutable version containing its
  number, author, time, parent, change summary, complete rules, and status.
- **FR-037**: TraderX MUST support at least `DRAFT`, `RESEARCH`, `BACKTESTING`, `VALIDATING`,
  `BACKTEST_PASSED`, `PAPER_READY`, `PAPER_TRADING`, `PAPER_PASSED`, `AWAITING_APPROVAL`,
  `LIVE_APPROVED`, `LIVE`, `WATCH`, `SUSPENDED`, `FAILED`, `REJECTED`, `RETIRED`, and `STALE` states.
- **FR-038**: Invalid lifecycle transitions MUST be rejected with the unmet prerequisites shown.
- **FR-039**: Users MUST be able to start historical tests with a range, initial equity, risk
  policy, trading-cost assumptions, execution assumptions, and prop-firm profile.
- **FR-040**: Historical reports MUST show trades, wins/losses, win rate, average win/loss,
  expectancy, average R, profit factor, total and daily drawdown, losing streak, risk-adjusted
  returns, MAE, MFE, exposure, and return.
- **FR-041**: Historical reports MUST support breakdowns by year, month, session, weekday, hour,
  direction, volatility regime, market regime, and event proximity where the data supports them.
- **FR-042**: TraderX MUST separate development, validation, and out-of-sample evidence and MUST NOT
  qualify a strategy solely on development data.
- **FR-043**: TraderX MUST support rolling or walk-forward evaluation where sufficient history
  exists and report window counts, profitable and losing windows, efficiency, and consistency.
- **FR-044**: TraderX MUST assess parameter stability and identify stable, potentially overfit, and
  highly sensitive results.
- **FR-045**: TraderX MUST support Monte Carlo or equivalent resampling and report drawdown
  distribution, extreme drawdown, losing-streak likelihood, prop-limit breach likelihood, and
  risk-of-ruin estimate.
- **FR-046**: TraderX MUST evaluate strategies together using chronological competition, one
  shared account, dynamic risk, correlation, daily and total limits, prop-firm rules, and the
  absolute two-position maximum.

#### Paper Trading and Human Approval

- **FR-047**: Only a strategy that passes configured historical requirements MUST be eligible for
  paper trading.
- **FR-048**: Paper trading MUST use current market data, the same strategy version used for signal
  generation, current risk rules, and realistic execution and transaction-cost assumptions.
- **FR-049**: TraderX MAY automatically open and manage simulated positions but MUST distinguish
  them clearly from real-money positions.
- **FR-050**: Paper requirements MUST combine configurable calendar duration, number of trades,
  expectancy, maximum drawdown, regime diversity, historical consistency, and prop-rule breaches;
  no single duration or trade-count threshold is sufficient.
- **FR-051**: TraderX MUST compare paper outcomes with historical expectations and send material
  divergence to review, research, or failure rather than automatic promotion.
- **FR-052**: Passing paper requirements MUST move a strategy to `AWAITING_APPROVAL`, never directly
  to a live state.
- **FR-053**: An authorized user MUST explicitly approve, reject, or return a strategy to research,
  and the decision and rationale MUST be audited.
- **FR-054**: Only `LIVE_APPROVED` or `LIVE` strategy versions with current evidence MUST produce
  actionable live recommendations.

#### Opportunities, Capacity, and Recommendations

- **FR-055**: TraderX MUST continuously evaluate all active markets using their eligible live
  strategies while reliable required data is available.
- **FR-056**: Every candidate opportunity MUST be assessed using strategy fit, regime, signal
  quality, volatility, liquidity, spread, expected reward-to-risk, event risk, historical and
  current strategy health, and portfolio risk where applicable.
- **FR-057**: TraderX MUST rank valid opportunities for scarce account capacity, but rank MUST NOT
  authorize a trade or override the Risk Manager.
- **FR-058**: The Risk Manager MUST issue the final deterministic `PASS` or `BLOCKED` decision for
  every actionable recommendation.
- **FR-059**: TraderX MUST calculate available live position capacity as zero, one, or two and MUST
  never allow more than two simultaneous live positions.
- **FR-060**: Before a second recommendation passes, TraderX MUST evaluate current and combined
  risk, correlation, common-factor exposure, remaining daily and overall loss margin, and remaining
  prop-firm safety margin.
- **FR-061**: Any attempted third live position MUST be blocked automatically with an explicit
  maximum-capacity reason.
- **FR-062**: TraderX MUST calculate suggested volume from current equity, risk percentage and
  amount, entry, stop distance, tick size/value, contract size, minimum volume and step, and
  existing portfolio risk.
- **FR-063**: A recommendation MUST include instrument and category, strategy and immutable version,
  direction, entry zone, stop, targets, expected reward-to-risk, permitted risk percentage and
  amount, suggested volume, opportunity score, risk decision and rationale, invalidation, and
  expiration.
- **FR-064**: Recommendations MUST expire on configured time, price, candle-close, structure-change,
  or strategy-invalidation conditions and MUST become visibly non-actionable.
- **FR-065**: `READY`, `WATCH`, `WAIT`, `BLOCKED`, and `NO TRADE` MUST be supported outcomes;
  TraderX MUST NOT manufacture an actionable trade when requirements are unmet.
- **FR-066**: TraderX V1 MUST contain no normal production capability that submits, changes, or
  closes a real-money order automatically.

#### Position Detection, Monitoring, and Journal

- **FR-067**: TraderX MUST receive current account and position information from the configured
  broker connection often enough to maintain safe risk decisions.
- **FR-068**: A newly detected position MUST be linked to a matching TraderX recommendation or
  classified as discretionary, and the user MUST be able to correct the classification.
- **FR-069**: Every detected live position MUST immediately affect equity, open risk, correlation,
  risk state, available capacity, and subsequent recommendations.
- **FR-070**: For a recommended trade, TraderX MUST freeze the strategy version, original regime,
  entry evidence and price, stop, targets, expected reward-to-risk, risk, and invalidation rules.
- **FR-071**: TraderX MUST monitor open positions against the frozen thesis and support `STRONG`,
  `HEALTHY`, `WATCH`, `WEAKENING`, and `INVALIDATED` health states.
- **FR-072**: Monitoring MAY produce hold, watch, profit-protection, thesis-weakening,
  thesis-invalidated, and risk-warning guidance but MUST NOT execute live orders.
- **FR-073**: Suspending a strategy MUST prevent new recommendations while preserving monitoring of
  its existing positions.
- **FR-074**: TraderX MUST maintain journal records for recommended, discretionary, and paper
  trades, including available execution, strategy, risk, thesis, monitoring, profit/loss, and R
  information.
- **FR-075**: Users MUST be able to add notes, reasons, emotion, confidence, FOMO, revenge behavior,
  rule deviations, stop changes, early exits, screenshots, and lessons.
- **FR-076**: Journal analytics MUST support comparison by instrument, asset class, strategy and
  version, session, weekday, hour, direction, risk state, entry quality, behavior, market regime,
  and volatility regime.
- **FR-077**: TraderX MUST continuously compare live strategy results with historical and paper
  ranges and MUST support watch, suspension, retirement, and research recommendations.
- **FR-078**: Journal and strategy-health findings MAY create research hypotheses but MUST NOT
  silently alter or approve a strategy.

#### Notifications, Integrations, Operations, and Audit

- **FR-079**: TraderX MUST create channel-independent notification events with `INFO`, `ACTION`,
  `WARNING`, and `CRITICAL` severities.
- **FR-080**: Users MUST be able to configure notification channels and preferences for trade,
  thesis, risk, validation, strategy, integration, and system-health events.
- **FR-081**: Authorized users MUST be able to connect, test, reconnect, enable, disable, inspect,
  and rotate credentials for broker, market, economic, macro, cryptocurrency, email, and messaging
  integrations through the UI where applicable.
- **FR-082**: Sensitive credentials MUST remain encrypted when stored, masked when displayed,
  absent from ordinary logs, access-controlled, and rotatable.
- **FR-083**: Every external data source MUST expose status, last success, freshness, latency, and
  current error, with at least `HEALTHY`, `DEGRADED`, `FAILED`, and `DISABLED` states.
- **FR-084**: Missing, stale, contradictory, or unverifiable critical market, account, instrument,
  or risk data MUST block new live recommendations while safe monitoring, journaling, research,
  validation, and paper work may continue.
- **FR-085**: Users MUST be able to view long-running research, synchronization, testing,
  simulation, paper, and maintenance work as queued, running, paused, completed, failed, or
  cancelled and perform only valid start, pause, cancel, retry, progress, and result actions.
- **FR-086**: Research, data collection, validation, paper trading, monitoring, and notifications
  MUST continue when the user's browser is closed.
- **FR-087**: TraderX MUST automatically activate circuit breakers for internal loss, drawdown,
  prop-firm safety, unknown equity, stale broker information, required-data failure, abnormal
  execution, strategy malfunction, or critical platform failure.
- **FR-088**: Circuit breakers MUST block new live recommendations and MAY leave safe monitoring,
  journaling, research, validation, and paper work available.
- **FR-089**: TraderX MUST audit authentication and security events, rule changes, integration
  changes, market activation or replacement, strategy approval/suspension/retirement, circuit
  breaker actions and overrides, and other material risk changes.
- **FR-090**: Audit records MUST identify actor, action, timestamp, reason, and previous/new values
  where applicable and MUST be available only to authorized users.
- **FR-091**: High-risk changes MUST present their effect, require deliberate confirmation and a
  reason, and be eligible for reauthentication or MFA before taking effect.
- **FR-092**: Every ordinary user and administrative workflow in this specification MUST be
  completable through the authenticated web interface without direct technical interfaces,
  configuration files, or administrator-only operational tooling.
- **FR-093**: Production external information MUST come from approved official connections or
  datasets; production behavior MUST NOT depend on web scraping.
- **FR-094**: AI assistance MAY summarize, explain, identify anomalies, and propose hypotheses, but
  MUST NOT override the Risk Manager, change risk, approve or modify strategies, disable safety,
  bypass evidence gates, or execute live orders.

### Key Entities

- **User**: An authenticated person with an identity, role, MFA state, active sessions, and
  authorization history.
- **Trading Account**: The single V1 live account with currency, balance, equity, positions,
  prop-firm profile, internal risk policy, and current risk state.
- **Prop-Firm Profile**: External account loss, drawdown, reset, consistency, news, weekend, and
  instrument restrictions.
- **Risk Policy**: TraderX's stricter per-trade, portfolio, loss, drawdown, correlation, capacity,
  reward-to-risk, and profit-protection constraints.
- **Instrument**: A broker-supported Commodity, Forex pair, or Cryptocurrency pair with contract
  specifications, data and execution status, active state, and permanent knowledge history.
- **Market Research Run**: A versioned evaluation of a category's candidate universe, eligibility
  gates, volatility/liquidity evidence, suitability method, rankings, recommendation, and approval.
- **Strategy**: A named trading hypothesis associated with an instrument and one or more immutable
  versions.
- **Strategy Version**: An immutable deterministic rule set with lifecycle status, ancestry,
  research context, evidence, and approval history.
- **Validation Run**: A historical, unseen-data, walk-forward, robustness, Monte Carlo, or portfolio
  evaluation tied to exact strategy, data, cost, and risk assumptions.
- **Paper Run**: Current-data simulated trading evidence tied to a strategy version and promotion
  requirements.
- **Opportunity**: A time-bounded assessment produced by a live-eligible strategy for an active
  instrument, prior to final risk authorization.
- **Recommendation**: A complete, expiring, Risk Manager-approved decision package that the trader
  may execute manually.
- **Position**: A broker-reported or simulated exposure classified as recommended, discretionary,
  or paper and included in shared risk.
- **Trade Thesis**: The immutable original evidence, regime, levels, risk, and invalidation rules
  associated with a recommended position.
- **Journal Entry**: The automatic and human-supplied execution, behavior, outcome, R, and lesson
  record for a trade.
- **Integration**: An approved external connection with protected credentials, status, freshness,
  and operational history.
- **Background Job**: Long-running research, data, validation, simulation, paper, or maintenance
  work with observable state, progress, and result.
- **Notification Event**: A severity-rated business event delivered through user-selected channels.
- **Audit Event**: An immutable record of a material security, risk, market, strategy, integration,
  or safety action.

### Scope Boundaries

**In scope for TraderX V1**:

- one primary shared-equity live account, including prop-firm constraints;
- three active categories with one user-approved instrument in each;
- research of additional inactive instruments without live ranking;
- research, explicit strategy creation, historical and robustness validation, portfolio testing,
  paper trading, human approval, opportunity ranking, position sizing, manual live execution,
  broker-position detection, thesis monitoring, journaling, analytics, notifications, audit, and
  system operations through the authenticated UI.

**Out of scope for TraderX V1**:

- automatic submission, modification, or closure of real-money orders;
- more than one primary live account, more than three active live markets, or more than two
  simultaneous live positions;
- high-frequency trading, martingale or revenge sizing, automatic risk increases after losses,
  automatic strategy promotion, AI control of deterministic risk, or production web scraping;
- guarantees of profitability or replacement of the trader's responsibility for live execution.

### Dependencies

- The user has access to a supported broker account and may lawfully connect it to TraderX.
- Approved data sources provide sufficient historical and current information for the instruments
  and analyses selected by the user.
- Broker/account information includes enough contract and position data to calculate risk and
  volume safely; otherwise live recommendations remain blocked.
- Notification delivery depends on at least one user-configured supported channel.
- Research and validation quality depends on the completeness and reliability of source data and
  on user-supplied account and prop-firm rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of first-time owners can authenticate, connect one account, configure
  external and internal risk rules, and reach a populated Command Center in 15 minutes or less
  without technical assistance.
- **SC-002**: In acceptance testing, 100% of attempts to access operational data without
  authentication and 100% of unauthorized high-risk actions are denied and recorded.
- **SC-003**: For at least 95% of ordinary Command Center refreshes, users see current account risk,
  position capacity, active markets, and critical alerts within 5 seconds.
- **SC-004**: Every completed market-universe run shows all evaluated candidates, every exclusion
  reason, comparable volatility/liquidity evidence, suitability method version, rank, and rationale
  before the user approves an active instrument.
- **SC-005**: In eligibility testing, 100% of candidates that fail a mandatory liquidity, data,
  execution, sizing, broker, or prop-firm gate are excluded before final ranking.
- **SC-006**: Users can approve exactly one eligible Commodity, Forex pair, and Cryptocurrency pair,
  and no ranking update changes an active instrument without explicit approval.
- **SC-007**: In lifecycle testing, 100% of invalid strategy transitions are rejected, and no
  strategy reaches live eligibility without recorded unseen-data validation, required robustness
  evidence, qualifying paper results, and authorized human approval.
- **SC-008**: Every strategy result can be reproduced from its recorded version, data range,
  parameters, assumptions, costs, risk policy, and random seed where applicable.
- **SC-009**: In risk-boundary testing, 100% of attempted third positions, positions beyond current
  dynamic capacity, and recommendations in `LOCKDOWN` are blocked with a user-visible reason.
- **SC-010**: In fail-safe testing, 100% of cases with missing or invalid critical equity, position,
  price, contract, or risk data produce no new live recommendation.
- **SC-011**: Every actionable recommendation presents all required entry, exit, risk, size,
  strategy, rationale, invalidation, and expiration information before the trader decides whether
  to act.
- **SC-012**: At least 95% of supported broker position changes become visible to the trader and
  affect displayed shared risk and capacity within 60 seconds of being available from the broker.
- **SC-013**: At least 95% of critical thesis, strategy, integration, or risk events are visible in
  the application and dispatched to enabled notification channels within 60 seconds of detection.
- **SC-014**: Every closed supported trade has a journal record containing available execution,
  risk, strategy or discretionary classification, outcome, and R information within 60 seconds of
  final trade data becoming available.
- **SC-015**: Replacement and reactivation testing preserves 100% of an instrument's prior research,
  strategy versions, validation, trading, journal, and market-selection evidence.
- **SC-016**: Across moderated usability tests, at least 90% of users complete each core workflow—
  market selection, strategy validation, approval, recommendation review, trade monitoring,
  journaling, and integration management—without direct technical tools or administrator help.
- **SC-017**: Acceptance testing finds no production path by which TraderX submits, modifies, or
  closes a real-money order automatically.
- **SC-018**: At least 90% of test users can explain from the displayed evidence why a market was
  selected, why a recommendation passed or was blocked, how its size was derived, and why the
  current position capacity is zero, one, or two.

## Assumptions

- TraderX V1 serves a single primary manual trader or a small role-controlled team managing one
  shared-equity live account.
- The `OWNER` has final authority for account, risk, market activation, integration, and strategy
  approval decisions; delegated `ADMIN` permissions may be narrowed during planning.
- Email/password authentication, password recovery, session management, and TOTP MFA satisfy V1;
  passkeys may be added later without changing the product workflows.
- "Cryptocurrency" means a broker-supported cryptocurrency trading pair, not custody or transfer
  of crypto assets.
- Suitability weights are configurable by authorized users, but mandatory eligibility gates and
  the Risk Manager veto are not removable configuration.
- Paper execution may be automatic because no real capital is submitted; real-money execution is
  always manual.
- Data retention is indefinite for evidence tied to instruments, strategies, trades, risk, and
  audits unless a future legal requirement mandates a controlled retention policy.
- User-visible times in reports and audit history are presented consistently with the configured
  account reset time zone while preserving an unambiguous underlying timestamp.
- Temporary loss does not by itself invalidate a trade thesis; monitoring compares current
  evidence with the frozen strategy-specific invalidation rules.
- When no eligible instrument exists in a category, the slot remains inactive and live opportunity
  ranking proceeds only for approved categories; the system does not weaken eligibility gates to
  fill a slot.
- Desktop installation, mobile-native applications, multiple live accounts, and automatic
  real-money execution are outside V1 scope.
