<!--
Sync Impact Report

- Version change: 1.0.0 -> 1.1.0
- Modified principles:
  - Initial Market Selection Must Be Research-Driven -> Active Market Selection Balances
    Volatility and Deep Liquidity
  - Highest Volatility Means Highest Volatility Among Eligible Markets -> Eligibility Gates
    Precede Volatility Ranking
  - Market Selection Is Explainable -> Market Selection Is Reproducible, Versioned,
    Explainable, and Auditable
- Added sections:
  - Consolidated Core Principles
  - Operational and Product Constraints
  - Engineering and Delivery Quality Gates
  - Semantic-versioned Governance
- Removed sections: None; the foundational rules are consolidated by subject.
- Follow-up TODOs: None.
-->

# TraderX Constitution

**Status**: Foundational
**Product**: TraderX
**Application Type**: Authenticated, server-hosted web application

## Core Principles

### I. Capital Preservation Has Absolute Priority (NON-NEGOTIABLE)

TraderX MUST prioritize capital preservation first, consistent profitability second, and
trading frequency last. The Risk Manager MUST evaluate every actionable live recommendation
and has absolute authority to return `BLOCKED`, regardless of strategy, AI output, market rank,
opportunity score, or user-configured ranking. Missing or unreliable critical data—including
market state, account equity, available loss margin, strategy validity, or position risk—MUST
prevent new live recommendations. Accumulating losses MUST reduce permissible risk and MAY
reduce live capacity from two positions to one or zero. Martingale, revenge sizing, and any
automatic increase in risk intended to recover losses are prohibited.

Rationale: TraderX exists to protect shared trading capital; an opportunity is never more
important than account survival.

### II. Evidence Gates Every Strategy

Every strategy intended for live use MUST follow this lifecycle:

```text
RESEARCH -> HYPOTHESIS -> DEFINITION -> BACKTEST -> OUT-OF-SAMPLE VALIDATION
-> WALK-FORWARD VALIDATION -> ROBUSTNESS / MONTE CARLO
-> PORTFOLIO + PROP-RISK SIMULATION -> PAPER TRADING
-> PAPER PERFORMANCE VALIDATION -> HUMAN APPROVAL -> LIVE
```

No component MAY bypass a stage when doing so could increase live financial risk. Backtests MUST
model realistic spread, commission, slippage, contract, volume, and execution constraints where
available. Positive in-sample results are insufficient: unseen-data evidence is mandatory, and
walk-forward, neighboring-parameter, Monte Carlo, sequence-risk, and portfolio tests MUST be used
when the required data exists. Paper trading MUST use current data, production strategy logic,
current risk rules, and realistic execution assumptions. Successful automation MUST end at
`AWAITING_APPROVAL`; only an authorized human may grant `LIVE_APPROVED` status.

Rationale: Profitability claims are hypotheses until they survive independent, realistic, and
current evidence.

### III. Live Real-Money Execution Is Human-Controlled (NON-NEGOTIABLE)

TraderX V1 MUST NOT automatically submit real-money orders. It MAY automatically execute only in
backtest, paper, or demo environments. For real money, TraderX MAY analyze, rank, calculate,
recommend, explain, notify, monitor, and journal; the trader MUST place and manage broker orders
manually. `NO TRADE`, `WAIT`, and `BLOCKED` are first-class outcomes. Recommendations MUST expire
on a defined time or invalidation condition and MUST NOT remain actionable when stale.

Rationale: Human execution is the final control boundary between research software and live
capital.

### IV. Active Market Selection Balances Volatility and Deep Liquidity

TraderX MUST maintain exactly three primary Active Market Slots: one Commodity, one Forex pair,
and one Cryptocurrency pair. Slot occupants MUST NOT be hardcoded. Within each category, TraderX
MUST research the broker/API-supported universe and seek the highest-volatility instrument among
instruments possessing sufficiently deep liquidity and acceptable trading conditions. It MUST
never interpret "highest volatility" as permission to select an illiquid, impractical, or
un-sizeable market.

An instrument MUST pass data-quality, liquidity, execution-quality, broker, prop-firm, and
trading-feasibility gates before volatility ranking. The objective is meaningful volatility plus
enough liquidity to enter, manage, and exit efficiently while protecting shared account capital.
All selections and replacements require human confirmation through the authenticated UI.

Rationale: Raw volatility without liquidity and execution quality creates costs and risks rather
than usable opportunity.

### V. Shared Equity and Dynamic Capacity Govern the Portfolio

All instruments in the same configured account MUST share one equity and loss budget. TraderX
MUST allow no more than two simultaneous live positions, even though it monitors three active
markets. Available live capacity MUST be calculated dynamically as zero, one, or two using account
equity, realized and unrealized loss, daily and overall drawdown, open risk, remaining prop-firm
margin, correlation, exposure, strategy quality, and current risk state. A third position MUST be
blocked. The second position MAY be reduced or blocked because of common currency exposure,
return correlation, macro sensitivity, strategy correlation, or concurrent-loss behavior.

Rationale: Market slots organize opportunity; they do not create independent capital or position
allowances.

### VI. Ordinary Operation Is Authenticated and UI-First

TraderX MUST be a server-hosted web application accessed through a browser. Research, data
collection, backtesting, paper trading, monitoring, and notifications MUST continue server-side
when the browser is closed. Every ordinary operation MUST be controllable from the authenticated
web interface; users MUST NOT need to call APIs, run scripts or shell commands, edit environment
or YAML files, issue SQL, connect directly to databases, run containers, or start workers.

No operational interface may be anonymous. TraderX MUST provide secure password handling,
password reset, session management and revocation, logout, TOTP MFA, role-based authorization,
and audit logging. Roles MUST include at least `OWNER`, `ADMIN`, and `VIEWER`. Sensitive or
risk-increasing actions SHOULD require reauthentication or MFA.

Rationale: A safe trading system must be operable, observable, and governable without privileged
infrastructure knowledge.

### VII. Knowledge and Versions Are Permanent and Reproducible

Deactivating or replacing an instrument MUST NOT delete its market data, research, experiments,
strategies, versions, validation, simulations, trades, journals, or execution history. Reactivation
MUST search existing knowledge first, refresh only missing or stale data where providers permit,
and revalidate evidence according to staleness. Previous live approval MUST NOT imply current
approval.

Strategy versions MUST be immutable. A material strategy change creates a new version with its own
evidence and approval lifecycle. Research and market-selection methods MUST record enough context
to reproduce results, including instrument, provider, data range/version, parameters, assumptions,
cost model, engine and strategy versions, risk profile, objective, timestamps, and random seed
where relevant.

Rationale: Immutable evidence prevents hindsight rewriting and turns past work into durable,
auditable knowledge.

### VIII. Safety Is Deterministic, Explainable, and Auditable

Position limits, drawdown limits, sizing, prop-firm constraints, strategy lifecycle gates, and
circuit breakers MUST be deterministic and testable. AI MUST NOT be the sole implementation of
any financial safety control and MUST NOT override the Risk Manager, approve strategies, increase
risk, bypass validation, disable circuit breakers, execute live orders, or silently modify
strategies.

TraderX MUST preserve the evidence behind market selections, recommendations, blocks, sizing,
risk-state changes, approvals, suspensions, and overrides. Significant changes MUST be audited
with actor, action, previous and new values, timestamp, and reason. High-risk changes SHOULD
require a warning, explanation, reauthentication or MFA, recorded reason, explicit confirmation,
and audit entry.

Rationale: Financial decisions must remain inspectable after the fact and safety outcomes must not
depend on opaque or nondeterministic behavior.

### IX. External Data Is Official, Normalized, and Fail-Safe

Production data MUST enter through official APIs, broker interfaces, documented streams, approved
datasets, or user-provided datasets. Production features MUST NOT depend on web scraping.
Provider-specific connectors MUST normalize data behind TraderX contracts so strategies do not
directly depend on a provider. TraderX MUST track provider, timestamp, freshness, completeness,
latency, and quality where possible. Missing, stale, or invalid critical data MUST produce
`NO NEW TRADE`.

Rationale: Reliable and replaceable data sources are prerequisites for reproducible research and
safe live recommendations.

### X. Monitoring and Learning Never Rewrite History

When a manually executed live position is associated with a recommendation, TraderX MUST freeze
its original strategy version, entry, stop, targets, regime, risk, expected reward-to-risk,
evidence, and invalidation criteria. Monitoring MUST compare that original thesis with current
conditions and MAY report `STRONG`, `HEALTHY`, `WATCH`, `WEAKENING`, or `INVALIDATED`. Temporary
loss alone MUST NOT be treated as invalidation.

TraderX MUST journal recommended, discretionary, and paper trades, use R-multiple alongside
financial profit and loss, and feed observed evidence back into research. Journal analysis and AI
MAY propose hypotheses, but MUST NOT silently modify or promote a live strategy.

Rationale: TraderX learns from outcomes without contaminating the evidence that produced them.

## Operational and Product Constraints

### Market Selection and Active Universe

The required selection pipeline is:

```text
Broker/API Universe -> Asset Classification -> Data Quality Gate -> Liquidity Gate
-> Execution Quality Gate -> Prop-Firm Rule Gate -> Trading Feasibility Gate
-> Multi-Horizon Volatility Analysis -> Volatility + Liquidity Evaluation
-> Candidate Ranking -> Human Confirmation -> Active Market Slot
```

Liquidity assessment MAY use volume, turnover, bid/ask spread, market depth, order-book depth,
expected slippage, broker execution characteristics, and the ability to enter and exit efficiently.
Eligibility MUST also consider official data availability and freshness, historical coverage,
contract specifications, tick size and value, minimum volume and volume step, position-sizing
feasibility, gap risk, trading hours, broker availability, and prop-firm permission.

Volatility MUST be assessed across short-, medium-, and long-term windows rather than a single
session. Measures MAY include realized and annualized volatility, rolling return standard
deviation, ATR and ATR percentage, average and intraday range, downside volatility,
volatility-of-volatility, regime, and historical range distribution.

TraderX SHOULD produce a multidimensional Market Suitability Score using volatility opportunity,
liquidity, execution, data quality, and strategy opportunity, less spread cost, slippage, gap, and
prop-firm risk. Exact weights MAY evolve, but every methodology MUST be reproducible, versioned,
explainable, and auditable. The UI MUST show candidate ranks, eligibility failures, supporting
metrics, methodology/version, research time and data range, selected instrument, and reasons.

Rankings MAY be refreshed as conditions change, but TraderX MUST NOT silently replace an active
instrument. The user chooses `KEEP`, `REVIEW`, or `APPROVE REPLACEMENT`. Inactive markets MAY still
be researched; only the three active markets participate in live opportunity ranking.

### Strategy Lab and Evidence Requirements

The authenticated UI MUST provide research history, experiments, a no-code strategy builder,
strategies and immutable versions, backtesting, out-of-sample validation, walk-forward analysis,
Monte Carlo and sequence-risk analysis, portfolio testing, paper trading, approval, strategy
health, suspension, and retirement. Users MUST be able to configure and run research without
programming.

Each strategy MUST explicitly define, where applicable, its instrument, direction, regime,
session, entry, confirmation, filters, event restrictions, stop, targets, trailing logic,
invalidation, expiration, and risk constraints. Opaque AI output does not constitute a strategy.

The lifecycle MUST support at least:

```text
DRAFT, RESEARCH, BACKTESTING, VALIDATING, BACKTEST_PASSED, PAPER_READY,
PAPER_TRADING, PAPER_PASSED, AWAITING_APPROVAL, LIVE_APPROVED, LIVE,
FAILED, REJECTED, WATCH, SUSPENDED, RETIRED, STALE
```

Historical validation MUST report at least trade count, win/loss rates, expectancy, average R,
average winner and loser, profit factor, maximum total and daily drawdown, losing streak, MAE,
MFE, exposure, and performance by year, session, regime, and direction. Paper promotion criteria
MUST combine configurable calendar duration, trade count, expectancy, drawdown, regime diversity,
historical consistency, and prop-rule compliance; time or trade count alone is insufficient.
Material backtest/paper divergence requires investigation, not promotion.

Portfolio validation SHOULD simulate chronological signal competition, shared equity, dynamic
capacity, correlation, maximum two positions, prop limits, and stricter TraderX limits. An
individually profitable strategy MAY be rejected if it worsens portfolio risk materially.

### Portfolio Risk and Recommendations

TraderX MUST distinguish broker equity, prop-firm risk equity, and internal TraderX risk equity.
It MUST support configurable initial balance, daily loss, maximum drawdown, static or trailing
drawdown, floating-loss treatment, reset time, consistency rules, news and weekend restrictions,
permitted instruments, and account-specific rules. Internal thresholds MAY be stricter than prop
limits; external limits are emergency boundaries, not target budgets.

Risk states MUST include `NORMAL`, `CAUTION`, `DEFENSIVE`, and `LOCKDOWN`, with UI-configurable
thresholds. `LOCKDOWN` permits no new position. Circuit breakers MUST stop new live
recommendations when internal loss limits, prop safety boundaries, drawdown thresholds, stale or
missing critical data, unknown equity, strategy malfunction, abnormal execution, or critical
platform failure make safe recommendation impossible. Monitoring, journaling, research,
backtesting, and paper trading MAY continue when safe.

Authorized users MUST be able to configure per-trade risk, portfolio risk, daily loss, drawdown,
position limit up to the constitutional maximum, correlation, consecutive-loss controls,
profit-protection, risk-state thresholds, and prop rules through the UI without code changes.

Opportunity scores rank scarce-capacity use but never authorize trades. Each actionable
recommendation MUST include, where applicable, instrument, direction, strategy and version,
score, entry zone, stop, targets, expected reward-to-risk, permitted risk, calculated volume,
current account risk, capacity, rationale, invalidation, and expiration. Sizing MUST use actual
equity, stop distance, tick size/value, contract size, minimum volume and step, and existing risk;
generic hardcoded pip assumptions are prohibited.

TraderX SHOULD detect manually opened broker positions through official integrations. Every
detected position, including discretionary positions, MUST immediately affect equity, risk,
capacity, correlation, state, and subsequent recommendations.

### Monitoring, Journal, and Notifications

Live monitoring MUST be thesis-based and MAY consider structure, regime, momentum, volatility,
expected adverse excursion, event risk, strategy conditions, and original invalidation. It MAY
recommend `HOLD` while a thesis remains valid or issue a warning when evidence deteriorates; the
human retains execution control.

The journal MUST automatically capture available instrument, account, strategy, entry/exit,
stops, targets, profit/loss, R, time, risk state, recommendation, thesis, and monitoring events.
The UI MUST allow confidence, emotional state, rule deviations, early exits, stop changes, FOMO,
revenge behavior, notes, screenshots, and lessons.

Notifications MUST be provider-independent and support at least `INFO`, `ACTION`, `WARNING`, and
`CRITICAL` severities. Material changes SHOULD notify; ordinary price noise SHOULD NOT.

### Security, Integrations, and System Control

Only appropriately authorized users may change risk or prop rules, approve or suspend strategies,
configure brokers, manage credentials or users, or disable safety mechanisms. Credentials and
tokens MUST be encrypted at rest, masked in the UI, absent from logs, access-restricted, and
rotatable. Normal integration setup MUST use UI forms with connection testing; users MUST NOT edit
environment files.

The Command Center SHOULD expose balance, equity, realized and floating profit/loss, daily loss,
drawdown, remaining risk, prop safety buffer, risk state, capacity, positions, active markets,
opportunity ranks, and critical alerts. Risk MUST NOT be hidden. The UI MUST expose research,
backtest and simulation jobs, data synchronization, paper and live strategies, health,
integrations, notifications, workers, system health, and logs. Jobs SHOULD support start, pause,
cancel, retry, progress, and results where applicable.

## Engineering and Delivery Quality Gates

TraderX SHOULD begin as a modular web platform with a web frontend, application backend,
PostgreSQL, a job queue, and background workers. Authentication, connectors, research, strategy,
validation, paper trading, opportunities, portfolio risk, monitoring, journaling, and notifications
MUST have explicit module boundaries. Microservices, Kafka, Kubernetes, or other distributed
infrastructure MUST NOT be introduced without evidence of actual scale or isolation requirements.

Every feature specification, plan, task set, and implementation affecting financial decisions
MUST identify its deterministic rules, persisted evidence, authorization boundary, failure mode,
audit events, and test oracle. Safety-critical work MUST fail closed.

Automated tests MUST cover at minimum:

- zero, one, and two open positions plus an attempted third position;
- `NORMAL`, `CAUTION`, `DEFENSIVE`, and `LOCKDOWN` risk states;
- daily-loss, overall-drawdown, floating-loss, and correlation boundaries;
- missing account data, stale price data, provider failure, and abnormal execution;
- draft, failed-backtest, failed-paper, stale, and unapproved strategies attempting live use;
- liquidity and eligibility failures preceding volatility ranking;
- human confirmation for initial selection and active-market replacement;
- immutable strategy versions and preserved instrument knowledge;
- prohibition of automatic real-money order submission.

Integration tests MUST verify normalized provider contracts, broker/account reconciliation,
strategy lifecycle transitions, portfolio/risk interactions, circuit breakers, authentication,
authorization, audit trails, and notification delivery. Test fixtures MUST include realistic
instrument specifications and transaction costs. A change that can increase live financial risk
MUST NOT ship without passing its safety-boundary tests and deliberate authorized review.

Correctness, security, reliability, testability, maintainability, observability, and
reproducibility take precedence over architectural novelty and delivery speed.

## Governance

This constitution is the highest project-level governance authority for TraderX. Specifications,
plans, tasks, code, configuration, and operational procedures MUST comply with it. If another
project artifact conflicts with this constitution, the constitution prevails unless and until it
is formally amended.

Amendments MUST:

1. document the proposed rule and rationale;
2. identify affected principles, invariants, workflows, data, tests, and migrations;
3. receive explicit approval from the TraderX owner or delegated governing authority;
4. update this file, its semantic version, and `Last Amended` date in the same change; and
5. include a compliance and migration plan for affected implementation.

Constitution versions follow semantic versioning:

- **MAJOR**: incompatible governance changes, removals, or redefinitions of existing principles;
- **MINOR**: a new principle or materially expanded, backward-compatible obligation; and
- **PATCH**: wording, precision, or other non-semantic clarification.

Every feature specification and implementation plan MUST include a Constitution Check. Every code
review affecting governed behavior MUST verify compliance, evidence, and required safety tests.
Exceptions MUST be documented, time-bounded, approved by the owner, and MUST NOT weaken any
non-negotiable invariant without a constitutional amendment. Compliance MUST be reviewed whenever
a governed workflow changes and at least once before each production release.

The following changes always require an explicit constitutional amendment:

- more than three active live markets or a category other than one Commodity, one Forex, and one
  Cryptocurrency;
- more than two simultaneous live positions;
- automatic real-money execution;
- martingale or revenge sizing;
- AI authority to override the Risk Manager or deterministic controls;
- automatic strategy approval or promotion;
- bypassing research, validation, paper trading, or human approval;
- deleting historical instrument knowledge when changing markets;
- production dependence on web scraping; or
- bypassing prop-firm or internal risk controls.

The permanent constitutional invariants are:

1. Capital protection precedes profit and trade frequency.
2. The Risk Manager has absolute veto over every live recommendation.
3. TraderX maintains one active Commodity, one Forex pair, and one Cryptocurrency pair.
4. Slot occupants are dynamic, research-selected, deeply liquid, eligible, and user-approved.
5. Eligibility gates precede multi-horizon volatility ranking.
6. Maximum simultaneous live positions is two; dynamic risk may reduce capacity to one or zero.
7. All positions in the same account share equity and loss limits.
8. Accumulated loss reduces risk; martingale recovery is prohibited.
9. No strategy becomes live without research, validation, paper evidence, and human approval.
10. Strategy versions are immutable and changes require new evidence.
11. Real-money execution remains manual.
12. `NO TRADE` is valid and missing critical information prevents new recommendations.
13. External production data uses official interfaces, never scraping.
14. Ordinary operation occurs through the authenticated web UI.
15. Instrument knowledge is preserved and reactivation reuses valid evidence.
16. Old approval does not imply current validity.
17. AI cannot override deterministic financial safety.
18. Historical or paper profitability is evidence, never a promise.

**Version**: 1.1.0 | **Ratified**: 2026-08-12 | **Last Amended**: 2026-08-12
