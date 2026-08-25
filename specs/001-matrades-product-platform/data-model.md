# Data Model: Matrades Product Platform

**Date**: 2026-08-25
**Source**: [spec.md](./spec.md)
**Related contracts**: [contracts/](./contracts/)

## Modeling Conventions

- Persistent aggregate IDs use UUIDv7 or an equivalent sortable opaque identifier; provider symbols
  and user-facing names are never foreign keys.
- All records carry `created_at`; mutable aggregates also carry `updated_at` and `version` for
  optimistic concurrency. Times are UTC instants with source timezone/reset metadata where relevant.
- Financial values use fixed-precision decimals with explicit currency, unit, contract size, and
  rounding rule. Authoritative financial calculations never use binary floating point.
- User-owned aggregates carry `owner_id`; account-scoped records also carry `account_id`. Every query
  enforces scope before filtering or semantic ranking.
- Material decisions reference immutable snapshots and configuration versions rather than mutable
  current rows.
- Secrets are represented only by `credential_id`/`secret_version_id`; plaintext and ciphertext do
  not appear in domain events, agent context, or API responses.
- Soft deletion is allowed for ordinary configuration. Audit, approval, strategy-version, policy-
  version, risk, trade, and broker evidence is append-only or immutable after finalization.

## Identity and Security

### User

| Field | Type | Rules |
|---|---|---|
| id | ID | Primary key |
| email | normalized text | Unique, verified before activation |
| password_digest | protected text | Never returned or logged |
| status | enum | `REGISTERED`, `EMAIL_VERIFIED`, `MFA_CONFIGURED`, `ACTIVE`, `LOCKED`, `DISABLED` |
| email_verified_at | instant | Required for `EMAIL_VERIFIED` or later |
| active_mfa_enrollment_id | ID | Required for `ACTIVE` |
| security_version | integer | Incremented on credential/session-invalidating change |

### MFAEnrollment and RecoveryCode

`MFAEnrollment` stores user, method (`TOTP` initially), encrypted seed reference, verification time,
status, and replacement history. `RecoveryCode` stores a one-way digest, issued set, consumed time,
and revocation state. No recovery code can be read after initial issuance.

### Session and StepUpChallenge

`Session` stores user, token digest, issued/last-seen/expiry/revocation times, client metadata, and
the user's security version. `StepUpChallenge` stores session, required action/scope, nonce digest,
expiry, status, and successful verification time. A challenge is single-use and action-bound.

### AuditEvent

| Field | Type | Rules |
|---|---|---|
| id | ID | Immutable event ID |
| owner_id | ID | Required tenant scope |
| actor_type / actor_id | enum / ID | User, system, worker, bridge, or agent execution |
| action | enum/text | Versioned audit action |
| aggregate_type / aggregate_id | text / ID | Target |
| aggregate_version | integer | Version after mutation |
| occurred_at / recorded_at | instant | Both required |
| correlation_id / causation_id | ID | Trace chain |
| redacted_metadata | object | Schema validated; no secrets/private reasoning |
| previous_hash / event_hash | digest | Optional tamper-evident chain per owner/partition |

Audit events are immutable from normal application operations and retained under the material-
decision policy.

## Credentials, Connections, and Health

### Credential and SecretVersion

`Credential` contains owner, display name, provider/purpose, masked suffix, active secret version,
status, last verified/used time, and aggregate version. `SecretVersion` contains credential, vault
locator or ciphertext, external key version, creation/retirement times, and access policy. Only the
vault adapter may materialize plaintext in a scoped process memory window.

### Connection

| Field | Type | Rules |
|---|---|---|
| id / owner_id | ID | Scoped identity |
| type | enum | Model gateway/provider, market data, macro, positioning, calendar, news, broker, MT5 bridge, embedding, blob, notification |
| provider / name | text | Adapter key and display name |
| credential_id | ID? | Optional protected reference |
| configuration | object | Adapter-schema validated, secret free |
| enabled / priority | boolean / integer | One or more active connections per capability |
| status | enum | `UNTESTED`, `HEALTHY`, `DEGRADED`, `STALE`, `OFFLINE`, `DISABLED` |
| last_success_at / last_failure_at | instant? | Health history |

### HealthObservation

Append-only observation for a connection, agent, service, worker, or source. Stores status, check
type, source/recorded times, latency, freshness age/limit, error code, retry state, and correlation ID.
Current health is a projection; material decisions reference the observation used.

## Models, Agents, Prompts, and Execution

### Model and ModelProfile

`Model` stores runtime type (`CODEX_APP_SERVER` or `LITELLM`), provider, provider model ID, display
name, credential reference where applicable, enabled state, context limit, and declared
tool/structured-output/reasoning/vision capabilities. `ModelProfile` stores owner, name, immutable
runtime type, primary model, parameters, timeout, capability requirements, explicit-alternative flag,
and version. `ModelProfileFallback` orders compatible fallback models by priority. Every model in a
profile and fallback chain MUST use the profile's runtime type; `LITELLM` profiles require explicit
assignment before activation.

### AgentDefinition

Seeded fixed roles are:

`orchestrator`, `forex_research`, `metals_research`, `crypto_research`, `stocks_research`, `technical_analyst`,
`fundamental_analyst`, `sentiment_analyst`, `regime_analyst`, `strategy_selector`,
`strategy_researcher`, `strategy_assistant`, `critic`, `trade_monitor`, `journal`, and `performance`.

Each definition stores immutable logical ID, role/type, required/optional status, required
capabilities, default runtime type (`CODEX_APP_SERVER`), default tool-permission set, input/output
schema versions, and lifecycle status.

### AgentConfigurationVersion

| Field | Type | Rules |
|---|---|---|
| id / owner_id / agent_id | ID | One version per owner/agent configuration |
| enabled | boolean | Required agents cannot be disabled for workflows that require them |
| runtime_mode | enum | `DEFAULT_CODEX`, `EXPLICIT_LITELLM`; defaults to `DEFAULT_CODEX` |
| runtime_selection_source | enum | `PLATFORM_DEFAULT`, `AGENT_OVERRIDE`, `MODEL_PROFILE`; auditable |
| model_mode | enum | `INHERIT_ORCHESTRATOR`, `MODEL_PROFILE`, `CUSTOM_MODEL`; inheritance is valid only within the selected runtime |
| model_profile_id / custom_model_id | ID? | Mode dependent |
| parameter_overrides | object | Schema/range validated |
| timeout / retry_policy | duration / object | Bounded |
| system_prompt_mode / system_prompt_version_id | enum / ID? | Independent `INHERIT` or `OVERRIDE` |
| user_prompt_mode / user_prompt_version_id | enum / ID? | Independent `INHERIT` or `OVERRIDE` |
| tool_permission_set_version_id | ID | Cannot be changed by prompt/model mutation |
| status | enum | `DRAFT`, `VALID`, `INVALID`, `ACTIVE`, `RETIRED` |

Activation rejects a configuration whose model or fallback runtime differs from the selected
runtime. Assigning a LiteLLM connection or synchronizing its models never changes an active agent
configuration; the operator must create and activate a new explicit version.

### PromptVersion and ToolPermissionSetVersion

`PromptVersion` contains owner/scope, agent ID or platform scope, type (`SYSTEM` or `USER`), version,
content, allowed template variables, content digest, author, and active/retired state.
`ToolPermissionSetVersion` lists allowed tool/action/resource scopes and explicit denials. Both are
immutable after activation.

### AgentExecution

Stores workflow and agent IDs, configuration version, configured and actual runtime, runtime
selection source, configured and actual model/provider, same-runtime fallback/retry details, resolved
system and user prompt versions, tool permission version, tool-call summaries, evidence references,
schema version, input/output digests or protected references, source times, uncertainty/status, code
release, tokens/cost/latency, error code, and timestamps. It does not store secrets or private
chain-of-thought. A database constraint or service invariant rejects an execution whose actual
runtime differs from its selected runtime.

## Instruments, Market Data, and Research

### UnderlyingAsset, Instrument, VenueInstrument, and InstrumentAlias

`UnderlyingAsset` is the stable economic identity for a currency, metal, cryptoasset, company
equity, index, or other reference asset. It stores canonical name/code, classification, issuer where
applicable, and active/delisted state. Shared-underlying exposure links every wrapper back to this
identity.

`Instrument` is a provider-neutral market expression with immutable `asset_class` (`FOREX`,
`METALS`, `CRYPTOCURRENCY`, `STOCKS`), `instrument_type` (`SPOT`, `CFD`, `FUTURES`), underlying/base
and quote/settlement assets, canonical/root symbol, ownership or derivative semantics, and lifecycle
status. Spot, CFD, and futures expressions over the same underlying always have different IDs.

`VenueInstrument` maps an exact provider, broker, issuer, or exchange listing to one Instrument. It
stores venue/account scope where applicable, provider symbol, tradable/researchable capabilities,
mapping verification/version, and status. Broker-issued CFDs remain distinct by issuer; provider
symbols and `InstrumentAlias` values are never canonical IDs.

### InstrumentSpecificationVersion

Immutable effective-dated terms used by research, risk, reconciliation, and replay:

| Field group | Required contents |
|---|---|
| identity | venue instrument, version, effective interval, digest |
| units | quantity unit, contract multiplier/size, price precision, tick/point size and value |
| limits | minimum/maximum/increment, minimum notional, trading mode |
| currencies | quote, settlement, margin, and P&L currency |
| sessions | calendar, timezone, sessions, holidays |
| margin/costs | margin method/rates, commission/spread basis, financing/funding or swap terms |
| lifecycle | listing, close-only, suspension, expiry, notice, settlement, roll eligibility |
| provenance | source connection, source/received time, freshness, normalization version |

Type-specific validation requires custody/ownership and settlement for spot; issuer, reference
underlying, lot definition, leverage, long/short financing, triple-swap day, and cash-adjustment
policy for CFDs; and exchange, root, contract month, first-notice, last-trade, expiry, delivery or
cash settlement, multiplier, tick value, and margin for futures.

### FuturesSeries, FuturesContract, ContinuousFuture, and RollRule

`FuturesSeries` identifies a venue/root. `FuturesContract` identifies one dated executable contract
and stores listing/notice/last-trade/expiry/settlement fields and roll lineage. `ContinuousFuture`
stores a synthetic analytical series and adjustment method; it cannot be tradable or referenced by
HIL-2. A versioned `RollRule` defines safety buffers, liquidity/open-interest thresholds, and
selection method. A `FuturesChainSnapshot` preserves all eligible/excluded contracts, source cutoff,
and deterministically selected contract.

### CorporateAction and FinancingObservation

`CorporateAction` preserves point-in-time splits, dividends, rights, mergers, symbol changes,
spinoffs, suspensions, and delistings with source/version and effective/ex dates. Raw/as-traded data
remains separate from explicitly adjusted analytical series. `FinancingObservation` stores
effective-dated CFD financing, swap, funding, borrow, and cash-adjustment terms with provenance.

### ResearchLane, ResearchMatrixVersion, and ProviderBinding

`ResearchLane` is the unique `(asset_class, instrument_type)` key; the initial matrix has 12 lanes.
An immutable account-scoped `ResearchMatrixVersion` records required/enabled lanes, schedule version,
and policy. `ProviderBinding` maps a lane and capability to a prioritized connection and exact
provider/venue mapping, with authority purpose (`DISCOVERY`, `REFERENCE`, `EXECUTABLE_QUOTE`,
`HISTORY`, `CONTRACT_TERMS`, or `BROKER_RECONCILIATION`), verification, freshness policy, and
effective interval. Fallback never crosses instrument type or changes legal/execution semantics.

### MarketObservation

Common envelope for `Quote`, `TradePrint`, `Candle`, `OrderBookSnapshot`, `OrderBookDelta`,
`IndicatorObservation`, `MacroObservation`, and `PositioningObservation`:

| Field | Type | Rules |
|---|---|---|
| instrument_id / venue_instrument_id | ID | Canonical expression and exact source listing |
| asset_class / instrument_type | enum | Explicit research-lane identity |
| specification_version_id | ID? | Required when observation semantics depend on contract terms |
| source_time / received_at / normalized_at | instant | Preserve all clocks |
| sequence / source_event_id | text? | Dedupe and gap checks |
| value payload | typed object | Observation-specific schema |
| quality / freshness | enum | `VALID`, `SUSPECT`, `STALE`, `INVALID` |
| normalization_version | text | Reproducibility |
| source_connection_id | ID | Provenance |

Duplicate natural keys are rejected; out-of-order records remain queryable but do not overwrite a
newer latest-state projection.

### EconomicEvent

Stores source event ID/version, name, country/currency, scheduled UTC time and source timezone,
impact, previous/forecast/actual values, first-release versus revision markers, retrieved time,
freshness, and parser/normalization version.

### MarketFingerprint

Immutable, lane/listing/time-bound decision snapshot containing asset class, instrument type, exact
venue instrument or futures contract, specification version, technical, structure, liquidity,
volatility, macro, sentiment, intermarket, event, session and risk-state references; structured
classification and quality; evidence set; computation/agent versions; and code release.

### ResearchRun, ResearchLaneResult, ResearchCandidate, and MarketSelection

`ResearchRun` stores owner/account, matrix version, the 12 requested lane keys, shared source-cut
references, job/workflow state, aggregate status/counts, archive manifest/checksum, and version.
`ResearchLaneResult` stores run/lane, terminal state (`READY`, `NO_TRADE`, `NOT_CONFIGURED`,
`UNAVAILABLE`, `STALE`, or `BLOCKED`), specialist execution, exclusions, candidate, evidence,
freshness, error/capability/binding references, and completion time. Exactly one result exists per
requested lane.

`ResearchCandidate` references an immutable candidate ID, lane, exact venue instrument and dated
contract where applicable, specification version, rank/factors, fingerprint, evidence and source
cut. `MarketSelection` owns `MarketSelectionEntry` records keyed by lane, each linking the chosen
candidate, HIL-1 decision, effective/expiry times, and replacement lineage. A replacement must stay
within the same lane; unresolved lanes cannot progress to HIL-2.

Pre-matrix category-only records retain their original payload and receive `LEGACY_UNTYPED` migration
metadata. They remain auditable and readable, but no migration invents an instrument type, venue
listing, dated contract, or specification version. A legacy selection becomes reusable only through
an explicit verified mapping that creates a new typed selection version.

## Accounts, Policy, and Risk

### TradingAccount

Stores owner, display name, `PERSONAL` or `PROP_FIRM`, currency, nominal starting balance, broker
connection, program/ruleset, guardrail profile, execution mode (`MANUAL`), status, and active account-
snapshot reference. A prop account requires an active verified compatible ruleset.

### AccountSnapshot

Immutable consistent broker cut containing account and connection IDs, broker sequence/cutoff,
starting balance, current balance/equity, floating and realized daily P&L, used/free margin, high-water
values, daily and total drawdown, open position/order references, source/received times, freshness,
currency, cash balances, owned-asset balances, FX-rate references, and digest. It cannot combine
position, balance, and equity observations from incompatible cuts. Spot inventory is valued as owned
underlying; CFD and futures exposure remains derivative exposure and is never converted into spot
inventory.

### PropFirm, PropProgram, PropRuleset, and PropRule

`PropFirm` owns programs; a `PropProgram` defines account types/sizes; an immutable `PropRuleset`
contains source, effective interval, version, verification/activation state and account scope;
`PropRule` stores typed operator/value/unit, drawdown/reset basis, scope, severity, source reference,
and effective interval. Only one compatible verified ruleset version is active for a decision.

### GuardrailProfile and GuardrailRule

Versioned internal rules with global/account/strategy scope, typed operator/value/unit, reset basis,
severity, effective interval, and author. A user rule may be stricter but never relax an external hard
rule.

### EffectiveConstraint and PolicyEvaluation

`EffectiveConstraint` records every contributing rule, normalized comparable value, controlling
source, and effective value. `PolicyEvaluation` stores immutable inputs, checks, `PASS`, `WARNING`,
`SOFT_BLOCK`, or `HARD_BLOCK`, reasons, ruleset/guardrail versions, and code release.

### PositionRiskReservation

Represents remaining worst-case loss for either an actual open position or actionable proposal.
Fields include account, proposal/position, amount/currency/base amount, Stop Loss and current-price
references, calculation version, status (`PROVISIONAL`, `AWAITING_ENTRY`, `OPEN_POSITION`, `RELEASED`,
`EXPIRED`), and expiry/release reason. Active reservations are included atomically in capacity.

### ExposureGroup and CorrelationRule

`ExposureGroup` maps instruments/factors to signed weights and category. `CorrelationRule` stores
scope, method, lookback, threshold/cap, fallback group, source data cutoff, and version. A computed
`ExposureSnapshot` stores gross/net/category/factor/correlated exposures and quality.

### RiskEvaluationContext and RiskCapacityResult

The context is immutable and references the candidate, exact venue instrument or futures contract,
instrument-specification version, account snapshot, active ruleset, guardrails, open positions,
active reservations, FX rates, instrument/broker terms, exposure model, market snapshot, and
freshness observations.

The result stores `PASS`, `REDUCE_SIZE`, or `HARD_BLOCK`; requested and compliant size; quantity unit;
notional exposure; initial/maintenance margin where applicable; risk amount and percentage; maximum
loss; daily/total/portfolio capacity before and after; reserved risk; projected direct/category/
correlated exposure; open count/ceiling; candidate-specific additional capacity; every limiting
constraint; calculation version; and expiry/revalidation trigger.

Validation invariants:

- A missing/stale/mismatched context or unbounded Stop Loss produces `HARD_BLOCK`.
- A compliant size rounds down to broker increments and never below a valid minimum.
- Sizing dispatches by instrument type: spot uses owned quantity and price, CFD uses lots and broker
  contract size, and futures uses whole contracts plus tick value/multiplier from the pinned contract.
- Margin is recorded as a funding constraint and is never treated as maximum loss.
- Exposure aggregates economically equivalent underlying risk across spot, CFD, and futures wrappers.
- Tightening a hard limit or adding loss/exposure cannot increase permitted size or capacity.
- Unrealized profit contributes only when the active policy explicitly defines it.
- A hard-block result cannot create an actionable approval.

## Strategy Platform

### StrategyFamily and PatternDefinition

Versioned taxonomy entries define applicable specification schema, mandatory/optional rule paths,
and compatibility categories. Pattern definitions hold deterministic meaning, parameters, evidence
requirements, and version; names alone are not executable logic.

### StrategyDraft and DraftRuleRevision

`StrategyDraft` stores owner, origin, name/description, base strategy/version lineage, family,
schema version, revision, status, completeness projection, and timestamps. `DraftRuleRevision` is an
immutable accepted/edit/generated rule change with rule path, typed value, source type,
suggestion/execution reference, actor, prior revision, and timestamp. Conversation is not canonical.

### StrategySuggestion and StrategyChangeSet

A suggestion stores draft/revision precondition, agent execution, rule path, current/suggested value,
explanation, evidence, warnings, uncertainty, and `PENDING`, `ACCEPTED`, `EDITED`, or `REJECTED`
status. A change set groups suggestions for atomic `ACCEPT_ALL`, individual review, or `REJECT_ALL`.
Idempotency and expected draft revision are required.

### Strategy and StrategyVersion

`Strategy` is the permanent identity: owner, origin, creator, family, canonical lineage, health and
current promoted version. `StrategyVersion` is immutable after specification: canonical rules,
schema version, content hash, parent version, authorship summaries, supported contexts/profiles,
status, implementation artifact, validation evidence, policy compatibility, code release, and dates.

### CanonicalFingerprint and SimilarityAssessment

The fingerprint contains canonical rule hash plus structural, parameter, semantic-description, and
behavioral signatures. An assessment links draft/version, candidates, per-dimension scores/evidence,
classification (`EXACT_DUPLICATE`, `NEAR_DUPLICATE`, `VARIANT`, `NEW_VERSION`, `NEW_STRATEGY`), and
allowed resolutions. Exact duplicates cannot resolve to `NEW_STRATEGY`.

### ImplementationArtifact

Versioned compiler output/reference containing strategy version, evaluator schema, compiler/code
version, deterministic rule graph, validation digest, and status. The same artifact contract is used
by backtest, paper, and live setup detection.

### BacktestRun, ValidationRun, PaperTradingRun, and PromotionDecision

`BacktestRun` references point-in-time data cutoff/version, artifact, exact venue listing or dated
futures contract, pinned specification/calendar/FX versions, corporate-action set, financing/funding
series, futures chain and roll rule when applicable, cost model, parameters, code, random seed,
outputs, metrics, and integrity checks. A continuous futures series is analytical input only and
cannot stand in for an executable dated contract. `ValidationRun` contains ordered stage results for
out-of-sample, walk-forward, stress/Monte Carlo, lifecycle/roll and corporate-action stress, and
account-policy simulation.
`PaperTradingRun` stores forward signals/executions, account simulation and minimum evidence.
`PromotionDecision` records criteria, evidence, user/system approver, decision, and audit linkage.

### StrategyCompatibility, StrategyHealth, and PerformanceRecord

Compatibility is versioned per account/ruleset/instrument/regime. Health records time-bound
`ACTIVE`, `DEGRADED`, `SUSPENDED`, or `RETIRED` evidence and do not mutate rules. Performance records
contain structured metrics, population size, time window and dimensions; narrative is separate.

## Knowledge

### KnowledgeSource

Stores owner, optional account/firm scope, type, name, enabled state, authorization policy, status,
last indexed/error times, active ingestion generation, and deletion state.

### KnowledgeDocument and KnowledgeSegment

Document fields include source, title/type, source reference, source version/date, content hash,
ingestion time/generation, metadata/tags, storage reference, authorization scope, and status.
Segments contain stable segment identity/index, content or protected reference, token count,
embedding vector/model/version/dimension, tags, generation and status.

### KnowledgeIngestionRun and RetrievalAudit

An ingestion run records parse/chunk/embed stages, idempotency, source/document counts, errors and
versions. Retrieval audit stores requester, permitted scope, query digest, filters, index/embedding
versions, returned document/segment IDs and scores, source times, correlation ID, and degradation;
it does not persist unnecessary sensitive query text.

Deletion purges retrievable content/embeddings and retains a minimal immutable tombstone. Retrieval
cannot return a disabled, deleted, unauthorized, or superseded segment unless an explicit historical
audit path permits metadata-only access.

## Trading Workflow, Broker State, and Approvals

### TradeProposal

Immutable proposal links owner/account, market fingerprint, validated strategy version/artifact,
construction values, evidence and invalidation, policy evaluation, risk context/result, critic
execution/result, freshness set, code version, state, expiry, risk reservation, and HIL-2 approval.
Only PASS or compliant REDUCE_SIZE results may enter `TRADE_PENDING_APPROVAL`.

### ApprovalRequest and ApprovalDecision

`ApprovalRequest` stores type (`MARKET_SELECTION`, `TRADE_ENTRY`, `TRADE_MANAGEMENT`), subject,
payload schema/version, allowed actions, urgency, status, expiry, expected subject version, and audit
correlation. `ApprovalDecision` stores exact action, actor, time, optional rationale, step-up context
where required, and resulting subject version.

Allowed actions are type-specific:

- HIL-1: `APPROVE`, `REPLACE`, `RERUN_RESEARCH`
- HIL-2: `TAKE`, `WAIT`, `REJECT`
- HIL-3: `APPROVE`, `WAIT`, `REJECT`

### BrokerPosition and BrokerEvent

`BrokerPosition` is the latest projection of provider position ID, account, canonical instrument,
exact venue listing or dated futures contract, asset class, instrument type, pinned specification,
direction, actual entry/size and quantity unit, Stop Loss/Take Profit, margin, financing/funding,
fees, P&L, broker version/timestamps, and freshness.
`BrokerEvent` is immutable and deduplicated by provider event/sequence; types include position opened,
changed/closed, protection changed/executed, and account changed.

### Reconciliation

Links proposal, detected position, match factors/scores, status (`CANDIDATE`, `AUTO_MATCHED`,
`USER_CONFIRMATION_REQUIRED`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`), user decision if ambiguous,
and actual-value snapshot. One broker position and one proposal can have at most one confirmed match.

### Trade, TradeRecommendation, and JournalEvent

`Trade` links proposal, account, strategy version, confirmed broker position, lifecycle status, open/
close times and outcome. `TradeRecommendation` stores HOLD or validated management action, evidence,
policy/risk effect, agent execution, expiry and HIL-3 linkage. `JournalEvent` is append-only and links
trade, event type, actor/source, structured payload, evidence/version references, broker event,
approval and timestamps.

### Notification

Stores normalized event type, owner, subject, urgency, channel attempts, delivery/read/acknowledgment
state, idempotency key, and timestamps. Notification delivery never changes approval state.

## Aggregate Relationships

```text
User
├── Credentials ── SecretVersions
├── Connections ── HealthObservations
├── AgentConfigurationVersions ── Prompt/Tool/Model versions ── AgentExecutions
├── TradingAccounts
│   ├── AccountSnapshots
│   ├── ResearchMatrixVersions ── ProviderBindings
│   ├── active PropRuleset + GuardrailProfile
│   ├── PositionRiskReservations + ExposureSnapshots
│   └── RiskEvaluationContexts ── RiskCapacityResults
├── UnderlyingAssets ── Instruments ── VenueInstruments ── SpecificationVersions
│   └── FuturesSeries ── DatedContracts/ChainSnapshots/RollRules
├── ResearchRuns ── 12 ResearchLaneResults ── MarketSelections ── HIL-1 Approvals
├── Strategies ── StrategyVersions
│   ├── Drafts ── RuleRevisions/Suggestions/ChangeSets
│   ├── Fingerprints/SimilarityAssessments
│   └── Implementation/Backtest/Validation/Paper/Promotion evidence
├── KnowledgeSources ── Documents ── Segments
└── TradeProposals ── HIL-2 Approval ── Reconciliation ── Trade
    ├── BrokerPosition/BrokerEvents
    ├── Recommendations ── HIL-3 Approvals
    └── JournalEvents ── PerformanceRecords
```

## State Transitions

### User activation and session

```text
REGISTERED -> EMAIL_VERIFIED -> MFA_CONFIGURED -> ACTIVE
PASSWORD_VERIFIED -> MFA_CHALLENGE -> AUTHENTICATED
AUTHENTICATED -> STEP_UP_PENDING -> STEP_UP_VERIFIED -> sensitive mutation
```

Invalid or expired challenges do not advance state. Security-version changes revoke older sessions.

### Connection and source health

```text
UNTESTED -> HEALTHY <-> DEGRADED -> STALE -> OFFLINE
any state -> DISABLED
DISABLED -> UNTESTED (explicit re-enable)
```

A newer valid observation is required to recover from STALE/OFFLINE. Status policy determines which
dependent workflows block or degrade.

### Strategy

```text
DRAFT -> SPECIFIED -> IMPLEMENTED -> BACKTESTING -> VALIDATING
      -> PAPER_TRADING -> APPROVED -> ACTIVE
ACTIVE -> DEGRADED -> ACTIVE | SUSPENDED
ACTIVE | DEGRADED | SUSPENDED -> RETIRED
```

Stages cannot be skipped. A material change creates a new DRAFT linked to an immutable source version.

### Research and market selection

```text
QUEUED -> RESEARCHING -> each requested lane reaches
  READY | NO_TRADE | NOT_CONFIGURED | UNAVAILABLE | STALE | BLOCKED
all lanes terminal -> MARKETS_PENDING_APPROVAL
MARKETS_PENDING_APPROVAL --APPROVE/REPLACE--> MARKETS_APPROVED
MARKETS_PENDING_APPROVAL --RERUN_RESEARCH--> RESEARCHING (new run/version)
any approved selection -> EXPIRED when its listing, contract, specification, or source cut expires
```

A replacement remains in its original `(asset_class, instrument_type)` lane. A missing provider
binding, mapping, authoritative contract specification, or dated futures contract produces an
explicit non-ready result and cannot silently fall back to another instrument type.

### Instrument mapping and lifecycle

```text
UNMAPPED -> MAPPED -> VERIFIED -> ACTIVE
ACTIVE -> STALE | SUPERSEDED | DELISTED

FUTURES_LISTED -> ACTIVE -> FIRST_NOTICE_APPROACHING | LAST_TRADE_APPROACHING
-> ROLL_REQUIRED -> EXPIRED | SETTLED
```

Corporate actions, broker-term changes, contract rolls, mapping changes, and specification-version
changes invalidate affected recommendations and force deterministic revalidation.

### Proposal and trade

```text
MONITORING -> SETUP_CANDIDATE -> POLICY_VALIDATION -> RISK_VALIDATION
RISK_VALIDATION -> HARD_BLOCKED | REDUCED | CRITIC_REVIEW
REDUCED -> CRITIC_REVIEW
CRITIC_REVIEW -> REJECTED_BY_CRITIC | TRADE_PENDING_APPROVAL
TRADE_PENDING_APPROVAL --TAKE--> AWAITING_MANUAL_ENTRY
TRADE_PENDING_APPROVAL --WAIT--> MONITORING
TRADE_PENDING_APPROVAL --REJECT--> TRADE_REJECTED
AWAITING_MANUAL_ENTRY -> POSITION_DETECTED -> POSITION_MATCH_PENDING
POSITION_MATCH_PENDING -> POSITION_ACTIVE | MATCH_REJECTED
POSITION_ACTIVE -> MANAGEMENT_PENDING_APPROVAL | TRADE_CLOSED
MANAGEMENT_PENDING_APPROVAL --APPROVE/WAIT/REJECT--> POSITION_ACTIVE
TRADE_CLOSED -> JOURNALED
```

At every transition, expired or changed authoritative inputs force revalidation. Broker-side
protective execution may move `POSITION_ACTIVE` directly to `TRADE_CLOSED` without HIL-3.

### Background job and knowledge ingestion

```text
QUEUED -> RUNNING -> SUCCEEDED
RUNNING -> RETRY_SCHEDULED -> RUNNING
RUNNING -> FAILED | CANCELLED

REGISTERED -> INGESTING -> INDEXED
INGESTING -> DEGRADED | FAILED
INDEXED -> REPROCESSING -> INDEXED
any source state -> DISABLED -> DELETING -> DELETED_TOMBSTONE
```

Job and ingestion transitions require idempotency keys; a retry cannot duplicate an accepted domain
mutation or active index generation.
