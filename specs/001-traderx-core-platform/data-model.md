# TraderX Core Platform Data Model

## Conventions

- Identifiers are opaque UUIDs. Provider identifiers are stored separately and scoped to an
  integration.
- All records include `created_at`; mutable records also include `updated_at` and integer `version`
  for optimistic concurrency.
- Timestamps are timezone-aware UTC. A named time zone is stored wherever prop-firm daily reset
  semantics depend on local civil time.
- Money, price, volume, ratios, tick values, and risk are fixed-precision decimals with an explicit
  currency or unit. Analytical arrays may use floating point, but persisted decision inputs and
  outputs use decimals.
- Durable evidence is append-only. Corrections create superseding records rather than rewriting
  strategy versions, completed runs, trade theses, risk decisions, or audit events.
- Secrets are represented only by encrypted credential references; decrypted values never appear
  in domain records, events, logs, or API responses.
- Domain events use a transactional outbox and carry aggregate identity/version, actor,
  correlation, causation, occurrence time, schema version, and idempotency key.

## Identity and Access

### User

| Field | Meaning / validation |
|---|---|
| `id` | Stable identity |
| `email` | Normalized, unique, verified before sensitive access |
| `password_hash` | Argon2id hash plus algorithm parameters; never returned |
| `role` | `OWNER`, `ADMIN`, or `VIEWER` |
| `status` | `INVITED`, `ACTIVE`, `LOCKED`, or `DISABLED` |
| `mfa_required` | Whether login requires an enrolled factor |
| `last_authenticated_at` | Used for reauthentication policy |

Relationships: owns sessions, MFA factors, recovery codes/challenges, password-reset challenges,
assisted-reset requests, and attributed audit events.

### IdentityBootstrapState

Singleton record with fixed key `1`, `owner_id`, and `initialized_at`. It is inserted in the same
transaction as the first `OWNER` and is never removed through ordinary operation.

Validation: its primary-key constraint allows exactly one first-owner setup. A conflicting
concurrent insert returns a bootstrap-unavailable result and creates no additional user.

### AuthSession

Fields: `id`, `user_id`, hashed session token, issue/expiry times, last-seen time, authentication
strength, client metadata, revoked time/reason, and session version.

Validation: expired, revoked, disabled-user, or version-mismatched sessions are invalid. Sensitive
commands require a recent authentication time and required MFA strength. `expires_at` is fixed to
12 hours after issue; inactivity exceeding 30 minutes invalidates the session without extending
the absolute expiry. Password, MFA, recovery, assisted reset, and privilege events revoke or
rotate the affected sessions.

### MfaFactor

Fields: `id`, `user_id`, factor type (`TOTP` in V1), encrypted secret reference, enrollment time,
confirmation time, last-used counter/time, and revoked time. Recovery codes are separately hashed
single-use records.

### MfaRecoveryCode

Fields: `id`, `user_id`, slow `code_hash`, issued time, used time, and replaced/revoked time.

Validation: plaintext codes are rendered only once after confirmed enrollment. A code can be
redeemed exactly once and its redemption atomically invalidates all sessions, replaces the active
factor with an unconfirmed TOTP enrollment, and appends audit/outbox facts.

### PasswordResetChallenge

Fields: `id`, `user_id`, hashed single-use reset token, issued/expiry/consumed times, and request
metadata needed for abuse detection.

Validation: a valid challenge permits password replacement only. A resulting operational session
requires a current TOTP code or unused recovery code; completion consumes the challenge and
revokes all existing sessions.

### AssistedMfaResetRequest

Fields: `id`, target `user_id`, initiating `OWNER` or `ADMIN`, initiating session/assurance,
explicit reason, confirmation time, initiated/completed/expired times, outcome, and audit-event
reference.

Validation: initiation requires recent MFA and authorized role. Completion follows the same
session/factor revocation and unconfirmed-enrollment path as recovery-code redemption; it never
creates a target-user operational session.

## Account and Risk

### TradingAccount

| Field | Meaning / validation |
|---|---|
| `id` | Account aggregate identity; only one `LIVE` account in V1 |
| `name` | User-facing name |
| `mode` | `LIVE`, `PAPER`, or `DEMO` |
| `currency` | ISO currency code |
| `broker_integration_id` | Enabled broker connection |
| `provider_account_id` | Encrypted or masked external identifier as appropriate |
| `starting_balance` | Positive decimal |
| `prop_profile_id` | Current external rule version |
| `risk_policy_id` | Current internal rule version |
| `status` | `DRAFT`, `CONNECTING`, `ACTIVE`, `DEGRADED`, `BLOCKED`, `DISABLED` |

### PropProfileVersion

Immutable fields: profile/name/version; starting balance; daily loss and maximum loss limits;
static/trailing drawdown method; high-water mark treatment; floating-loss inclusion; reset local
time, named zone, and holiday/weekend handling; news and weekend restrictions; consistency rules;
permitted/restricted instruments; effective time; author; reason.

### RiskPolicyVersion

Immutable fields: maximum risk per trade, maximum portfolio risk, internal daily loss and drawdown,
minimum prop buffer, maximum positions (validated `0..2`), correlation threshold, consecutive-loss
thresholds, minimum reward-to-risk, profit-protection rules, state thresholds, effective time,
author, and reason.

### AccountSnapshot

Append-only observation containing provider sequence/time, observed/received time, balance, equity,
realized and floating profit/loss, margin and free margin, broker-reported daily values, data
quality/freshness, and raw-payload reference. Unique on integration plus provider observation
identity to prevent double counting.

### RiskSnapshot

Derived, append-only view tied to exact `AccountSnapshot`, `PropProfileVersion`, `RiskPolicyVersion`,
and open-position set. Fields include effective equity, high-water mark, daily and total loss,
remaining external/internal margins, open and available risk, correlation/common-factor exposure,
consecutive losses, current `RiskState`, capacity (`0`, `1`, `2`), quality status, calculation
version, and reason codes.

`RiskState`: `NORMAL -> CAUTION -> DEFENSIVE -> LOCKDOWN`. Improvement is permitted only when the
configured policy and reset rules say the triggering conditions have cleared; loss recovery never
increases position size beyond ordinary policy.

### RiskDecision

Immutable fields: decision type (`PASS`, `PASS_REDUCED`, `BLOCKED`), opportunity/recommendation
identity, risk snapshot, requested and permitted risk/volume, capacity before decision, rule-set
version, reason codes and explanation inputs, calculation trace hash, time, and correlation id.

Validation: `PASS` requires verified critical inputs, capacity greater than zero, and resulting
open position count at most two. A score cannot change the decision.

### CircuitBreaker

| Field | Meaning |
|---|---|
| `type` | Daily loss, drawdown, prop buffer, unknown equity, stale data, risk failure, execution anomaly, platform failure |
| `scope` | System, account, integration, strategy, or instrument |
| `state` | `ARMED`, `TRIPPED`, `ACKNOWLEDGED`, `CLEARED` |
| `trigger_evidence` | Immutable facts and thresholds that caused the trip |
| `tripped_at` / `cleared_at` | Lifecycle timestamps |
| `acknowledged_by` / `reason` | Required for manual acknowledgement |

Transitions: `ARMED -> TRIPPED -> ACKNOWLEDGED -> CLEARED -> ARMED`. Clearing does not erase the
trip. A trip blocks new live recommendations for its scope while explicitly safe capabilities
remain available.

## Integrations and Jobs

### Integration

Fields: `id`, category (`BROKER`, `MARKET_DATA`, `ECONOMIC`, `MACRO`, `CRYPTO`, `EMAIL`,
`MESSAGING`), provider type, display name, enabled state, capability allowlist, configuration
without secrets, credential version reference, created/updated by, and concurrency version.

Validation: a live broker integration cannot advertise or invoke order-submission capabilities.
Production data integrations must be approved official connections or datasets, never scrapers.

### IntegrationCredentialVersion

Append-only metadata: integration, encrypted payload reference/ciphertext, key version, masked hint,
creator, rotation time, superseded time, and last successful verification. Plaintext is never
persisted outside the encryption boundary.

### IntegrationHealthObservation

Fields: integration, state (`HEALTHY`, `DEGRADED`, `FAILED`, `DISABLED`), observed/received times,
last success, latency, freshness, error category and redacted detail, and affected capabilities.

### BackgroundJob

Fields: `id`, job type, owner, aggregate/context reference, immutable input manifest, state,
priority, progress numerator/denominator/message, attempt count, cancel-requested time, lease owner
and expiry, result/error reference, queued/started/finished times, idempotency key, and parent job.

Transitions: `QUEUED -> RUNNING -> {PAUSED, COMPLETED, FAILED, CANCELLED}`; `PAUSED -> {QUEUED,
CANCELLED}`; retry creates a new attempt while preserving history. Cancellation is cooperative;
completed checkpoints/results remain immutable.

## Instruments and Market Data

### Instrument

Fields: `id`, canonical symbol, display name, category (`COMMODITY`, `FOREX`, `CRYPTO`), base/quote
assets where applicable, price/volume precision, contract size, tick size/value and tick-value
currency, minimum/maximum volume, volume step, trading calendar, gap-risk classification, status
(`ACTIVE`, `INACTIVE`, `ARCHIVED`), first/last seen, and last active time.

Deletion rule: instruments referenced by any evidence cannot be physically deleted.

### InstrumentAlias

Maps an `Instrument` to an `Integration` and provider symbol, contract variant, provider metadata,
validity interval, and verification status. Unique for provider plus provider symbol and interval.

### DataSetManifest

Immutable manifest for reproducible analysis: instrument, provider/alias, data kind and interval,
coverage bounds, row count, content/chunk hashes, calendar/time-zone normalization, quality report,
correction/supersession references, created time, and storage reference.

### MarketObservation

Normalized candle, quote, tick, spread, volume, or order-book observation. Common fields include
instrument, provider, event and receive times, sequence, quality flags, and raw reference. Kind-
specific values are decimal. Deduplication key is provider/alias/kind/interval/event identity.

### EconomicEvent

Fields: provider event identity, event time, affected currencies/markets, importance, title,
observed/forecast/previous values, revision, received time, and quality status.

### DataQualityObservation

Records completeness, freshness, latency, duplicates, gaps, outliers, timestamp ordering,
specification availability, result (`PASS`, `WARNING`, `FAIL`), thresholds, and evidence for a
provider/instrument/time range.

## Market Selection

### MarketResearchRun

Immutable run fields: category, candidate-universe definition, account, prop profile, methodology
version, dataset manifests, lookback windows, eligibility thresholds, score weights, random seed if
used, job/run state, started/completed times, initiator, and report reference.

### CandidateAssessment

Belongs to a research run and instrument. Stores each gate result and reason, raw and normalized
volatility/liquidity/execution/data/strategy/cost/gap/prop metrics, score components, final score,
rank, confidence/coverage, and explanation. Ineligible candidates have no selectable final rank.

### ActiveMarketAssignment

Append-only effective-dated assignment for one category: instrument, source research run and
assessment, status (`PENDING_APPROVAL`, `ACTIVE`, `REPLACED`, `DEACTIVATED`), effective interval,
approver, confirmation strength, reason, and replaced assignment.

Constraints: at most one effective `ACTIVE` assignment per category and at most three overall.
Activation requires an eligible assessment. Research never changes assignment automatically.

## Research, Strategies, and Validation

### ResearchJobDetail

Extends `BackgroundJob` with instrument, objective, historical range, strategy family, thresholds,
allowed indicators/regimes/sessions, dataset manifests, engine version, code revision, parameters,
assumptions, costs, risk profile, and random seed.

### ResearchExperiment

Immutable candidate hypothesis/result: research job, instrument, hypothesis, exact inputs,
candidate strategy definition, metrics, disposition (`CANDIDATE`, `REJECTED`, `INCONCLUSIVE`),
reason, and artifact references.

### Strategy

Stable identity with name, instrument, objective, owner, status summary, current draft version,
latest live version if any, and created/retired time. Rules never live directly on this record.

### StrategyVersion

Immutable fields: strategy, semantic version label, parent version, complete canonical rule
definition and schema version, definition hash, change summary, author, created time, lifecycle
state, instrument, and source research experiment.

Lifecycle:

```text
DRAFT -> RESEARCH -> BACKTESTING -> VALIDATING -> BACKTEST_PASSED
-> PAPER_READY -> PAPER_TRADING -> PAPER_PASSED -> AWAITING_APPROVAL
-> LIVE_APPROVED -> LIVE -> WATCH -> SUSPENDED -> RETIRED
```

`FAILED`, `REJECTED`, and `STALE` may be entered from applicable gates. A new rule definition
creates a child version; completed or validated versions are never updated in place.

### BacktestRun

Immutable run manifest: strategy version, datasets, development/validation split, initial equity,
cost and fill models, prop/risk versions, engine/code versions, seed, state/outcome, metrics,
breakdowns, equity curve and trade artifact references, and reproducibility hash.

### ValidationRun

Fields: strategy version, validation type (`OUT_OF_SAMPLE`, `WALK_FORWARD`,
`PARAMETER_STABILITY`, `MONTE_CARLO`, `PORTFOLIO`), prerequisite runs, input manifest, thresholds,
seed, metrics/distributions, result (`PASS`, `WARNING`, `FAIL`), evidence/reasons, and artifacts.

### PaperRun

Fields: strategy version, start/end, current datasets, production rule interpreter version,
execution/cost model, risk versions, promotion criteria, simulated positions/trades, metrics,
historical comparison, divergence result, state, and final disposition.

Transitions: `CONFIGURED -> RUNNING -> {PAUSED, REVIEW, PASSED, FAILED, CANCELLED}`. `PASSED` only
makes the strategy eligible for `AWAITING_APPROVAL`.

### StrategyApproval

Append-only decision: strategy version, eligibility snapshot, outcome (`APPROVE_LIVE`, `REJECT`,
`RETURN_TO_RESEARCH`), authorized actor, authentication strength/time, explicit reason, decision
time, and audit correlation. Approval cannot target a stale or superseded evidence set.

### StrategyHealthObservation

Fields: strategy version, time/window, live expectancy, win rate, drawdown, streak, MAE/MFE,
historical and paper divergence, regime evidence, result (`HEALTHY`, `WATCH`,
`SUSPEND_RECOMMENDED`, `SUSPENDED`), and reasons.

## Opportunities, Positions, and Monitoring

### Opportunity

Immutable evaluation of an active instrument and live-eligible strategy: signal time, strategy and
version, market snapshot/manifest, regime, direction, setup evidence, raw score components, score,
expected reward-to-risk, event/liquidity/strategy-health evidence, state (`READY`, `WATCH`, `WAIT`,
`BLOCKED`, `NO_TRADE`, `EXPIRED`), and expiry/invalidation rules.

### Recommendation

Created only after a passing `RiskDecision`. Fields: opportunity, instrument/category, strategy
version, direction, entry range, stop, ordered targets, expected reward-to-risk, permitted risk
percentage/amount, suggested volume, score, risk decision, complete reason/evidence references,
issued time, expiry/invalidation rules, state (`ACTIONABLE`, `EXPIRED`, `INVALIDATED`, `MATCHED`,
`WITHDRAWN`), and state time.

No recommendation is an order and no transition submits one.

### Position

Fields: account, environment (`LIVE`, `PAPER`, `DEMO`), provider position identity, instrument,
direction, volume, average entry, current stop/targets if observed, open/close times, current state,
classification (`RECOMMENDED`, `DISCRETIONARY`, `PAPER`), matched recommendation and confidence,
user-confirmed classification, latest provider sequence, and reconciliation status.

Constraints: provider updates are idempotent; all live positions count toward risk immediately;
classification correction never removes their historical risk effects.

### TradeExecution

Append-only fills/deals belonging to a position: provider identity, side, quantity, price, fees,
currency, event/receive time, sequence, and correction reference.

### TradeThesis

One immutable snapshot per recommended position: recommendation, strategy version, original regime,
entry evidence and price, stop, targets, expected reward-to-risk, initial risk, invalidation rules,
created time, and content hash.

### MonitoringObservation

Append-only comparison of a position and frozen thesis with current evidence, result (`STRONG`,
`HEALTHY`, `WATCH`, `WEAKENING`, `INVALIDATED`), reasons, recommended guidance (`HOLD`, `WATCH`,
`PROFIT_PROTECTION`, `THESIS_WEAKENING`, `THESIS_INVALIDATED`, `RISK_WARNING`), and event time.

## Journal, Notifications, and Audit

### JournalEntry

One trade-level record linked to position, paper trade, strategy/recommendation where applicable,
account/risk context, execution summary, profit/loss, R, timing, thesis, and monitoring history.
Automatic values are sourced; corrections are versioned.

### JournalAnnotation

Append-only user contribution: journal entry, author, type (note, reason, emotion, confidence, FOMO,
revenge, rule deviation, stop change, early exit, lesson), value, time, and superseded annotation.

### JournalAttachment

Fields: journal entry, uploader, protected artifact reference, media type, size, checksum, caption,
created time, and access classification.

### NotificationEvent and Delivery

`NotificationEvent` contains event type, severity (`INFO`, `ACTION`, `WARNING`, `CRITICAL`), subject,
deduplication key, template data without secrets, created/expiry time, and audit correlation.
`NotificationDelivery` records channel/integration, attempt, state (`PENDING`, `SENT`, `FAILED`,
`SUPPRESSED`, `EXPIRED`), provider identity, times, redacted error, and retry schedule.

### AuditEvent

Append-only fields: actor (user/system), action, target type/id/version, time, reason, correlation and
causation, authentication strength, source, outcome, redacted previous/new values, and integrity
hash. Audit records cannot be edited through ordinary application capabilities.

### OutboxEvent and ConsumerReceipt

`OutboxEvent` stores the versioned domain-event envelope and publication state in the same
transaction as its aggregate change. `ConsumerReceipt` uniquely records consumer plus event ID and
outcome so retries cannot apply a financial side effect twice.

## Relationship Summary

```text
User -> AuthSession / MfaFactor / MfaRecoveryCode / PasswordResetChallenge / AssistedMfaResetRequest / AuditEvent
IdentityBootstrapState -> User (exactly one initial OWNER)
TradingAccount -> PropProfileVersion / RiskPolicyVersion / AccountSnapshot -> RiskSnapshot
Integration -> CredentialVersion / HealthObservation / InstrumentAlias / Provider observations
Instrument -> DataSetManifest / MarketResearchRun / Strategy / ActiveMarketAssignment
MarketResearchRun -> CandidateAssessment -> ActiveMarketAssignment (human approved)
Strategy -> StrategyVersion -> BacktestRun / ValidationRun / PaperRun / StrategyApproval
StrategyVersion + ActiveMarketAssignment -> Opportunity -> RiskDecision -> Recommendation
TradingAccount -> Position -> TradeExecution / TradeThesis / MonitoringObservation / JournalEntry
Domain aggregate change -> OutboxEvent -> ConsumerReceipt -> NotificationEvent / AuditEvent
```
