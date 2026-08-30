# Implementation Plan: Matrades Product Platform

**Branch**: `001-matrades-product-platform` | **Date**: 2026-08-25 |
**Spec**: [spec.md](./spec.md)

**Input**: Consolidated feature specification from
`specs/001-matrades-product-platform/spec.md`, informed by the three supplied implementation
plans and governed by Matrades Constitution 3.0.0.

## Summary

Build Matrades V1 as a browser-based autonomous trading platform backed by a Python modular
monolith, durable background workers, a separately deployable execution-capable MT5 bridge, and a
TypeScript web application. PostgreSQL is the authority for configuration, workflow, policy,
risk, strategies, Trade Plans, execution commands, trades, and audit evidence; TimescaleDB and pgvector extend the
same data platform for time-series and contextual knowledge, while Redis remains non-authoritative.

The design removes HIL-1, HIL-2, and HIL-3 and enforces hard financial rules, per-account action
permissions, durable account/platform kill switches, broker-write authorization, idempotency, and
reconciliation in deterministic services. Declarative strategy rules compile into one shared
backtest/paper/live evaluator, while AI agents remain bounded by versioned contracts, independent
prompt resolution, least-privilege tools, and a default Codex App Server runtime pool. Agents never
receive broker credentials; structured Trade Plans and management actions reach brokers only through
the deterministic execution service. LiteLLM remains an explicit per-agent or per-profile alternative
and is never an automatic cross-runtime fallback.
Coinbase replaces Binance as the required V1 crypto exchange-data provider; `strategy_assistant`,
`stocks_research`, and the read-only `knowledge_assistant` complete the 17-agent registry; contextual
knowledge is isolated from authoritative market, account, policy, risk, and execution state.
Named data-source and MT5 Bridge profiles are configured in the UI, every market or
strategy research cycle is archived under a timestamped evidence folder, and provider-backed
backtests expose deterministic validation gates in the Strategy Lab.

Daily autonomous research fans out across the 12 combinations formed by Forex, metals,
cryptocurrency, and stocks crossed with spot, CFD, and futures. Each matrix cell produces one
ranked exact tradable listing or an explicit `NO_TRADE`, `NOT_CONFIGURED`, `UNAVAILABLE`, `STALE`,
or `BLOCKED` result and eligible candidates continue into analysis without approval.
Provider-neutral economic identities remain separate from broker/venue listings and dated futures
contracts, while immutable contract-specification versions drive sizing, costs, reconciliation,
backtesting, and cross-wrapper exposure aggregation.

During execution and monitoring, the UI displays each active Trade Plan beside a read-only live chart;
the Journal agent appends immutable observations that are indexed continuously for a citation-grounded,
read-only Knowledge Assistant. Analytics keep `BACKTEST`, `PAPER`, and `LIVE` populations separate,
and confirmed broker entries generate deduplicated notifications through enabled channels.

## Technical Context

**Language/Version**: Python 3.13 for backend, workers, deterministic engines, and research;
TypeScript 5.x on Node.js 24 LTS for the web application; declarative JSON/YAML for strategy and
contract artifacts

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy, Alembic; Celery 5.6 with Redis transport;
LangGraph for bounded workflow orchestration only; the stable `openai-codex` Python SDK with its
pinned Codex CLI/App Server runtime; optional LiteLLM Proxy; NumPy, Polars/pandas, SciPy, and
vectorbt where appropriate for research; Next.js 16 LTS, React, Tailwind CSS, accessible UI
primitives, TanStack Query, and a provider-neutral read-only financial chart component

**Storage**: PostgreSQL 17 as system of record with compatible TimescaleDB and pgvector extensions;
Redis for cache, rate limits, locks, and task transport only; effective-dated instrument
specifications, futures chains, corporate actions, financing terms, and point-in-time universe
membership are durable structured records; uploaded source documents and large artifacts use an
access-controlled blob abstraction when database storage is unsuitable

**Testing**: pytest, pytest-asyncio, Hypothesis, and integration containers for Python; Vitest and
Testing Library for TypeScript; Playwright for browser journeys; OpenAPI/schema and adapter contract
tests; deterministic replay, failure injection, and migration tests; matrix-coverage, contract-
version, futures-roll, corporate-action, CFD-financing, and cross-wrapper exposure fixtures

**Target Platform**: Linux containers for API, background workers, Codex agent workers, web,
database, and Redis; optional separately enabled LiteLLM Proxy containers; evergreen desktop
browsers; an authenticated MT5 bridge runnable on Windows, macOS/Wine, or a hosted Windows
environment

**Project Type**: Full-stack web application in a monorepo, delivered as a modular monolith plus
workers and a separately deployable broker bridge

**Performance Goals**: At least 95% of complete candidate evaluations return a decision or explicit
safe-failure status within 5 seconds after inputs are available; at least 95% of daily research runs
produce all 12 matrix-cell results or explicit per-cell safe-failure statuses within 10 minutes;
operational state and chart-overlay changes reach the UI within 2 seconds under normal conditions;
at least 99% of committed live journal events become searchable within 60 seconds when indexing is healthy

**Constraints**: Broker connections start read-only and require explicit per-account action
permissions before writes; active account/platform kill switches block new entries and discretionary
writes; current account equity and consistent snapshots are required before every entry or risk-
increasing action; strictest applicable constraint wins; hard-blocked candidates never reach the
execution service; broker commands are idempotent and uncertain outcomes reconcile before retry;
secrets never enter prompts, logs, or client responses; RAG is non-authoritative and the Knowledge
Assistant is read-only; every required agent defaults to the Codex App Server runtime;
LiteLLM requires an explicit per-agent or per-profile selection and cannot be an automatic fallback;
PostgreSQL, not Redis or an agent checkpoint alone, owns durable workflow, permission, kill-switch,
execution-command, and reconciliation state; all
timestamps are stored in UTC with source timezone metadata; every actionable instrument has a
fresh, immutable contract-specification reference; continuous futures are analytical only and
cannot be executed or reconciled as tradable contracts

**Scale/Scope**: V1 supports individual authenticated traders with multiple personal or prop-firm
accounts, 17 required logical agents including `stocks_research` and `knowledge_assistant`, 12 daily asset-class/instrument-
type research cells, multiple provider and broker mappings per cell, long-running research/backtest
jobs, and event-driven monitoring. Module and adapter boundaries permit later multi-user and service
extraction without adding V1 microservices.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Constitutional gate | Design evidence | Pre-design | Post-design |
|---|---|---|---|
| Ordered authority and deterministic safety | Kill switches, external rules, internal limits, account permissions, strategy rules, authoritative data, evidence, and bounded AI are evaluated in constitutional order before broker writes | PASS | PASS |
| Autonomous execution and human safety control | No HIL states remain; account action permissions, durable account/platform kill switches, deterministic execution authorization, idempotency, and reconciliation bound full-lifecycle automation | PASS | PASS |
| Account-aware risk and prop compliance | Immutable account snapshots, versioned rulesets, reserved risk, candidate reservations, correlated exposure, and type-specific contract/tick/margin/currency calculations | PASS | PASS |
| Equal strategy validation | AI-generated and AI-assisted proposals require human canonicalization approval and converge on one validation, paper, and promotion pipeline | PASS | PASS |
| Authoritative data and bounded RAG | Retrieval cannot supply current facts or commands; live journal indexing points to authoritative immutable events; exact listing, contract, broker, and performance records remain structured authority | PASS | PASS |
| Safe failure and NO TRADE | Health/freshness states, permission denials, kill switches, uncertain execution reconciliation, and circuit breakers make BLOCK, DEGRADED, WAIT, and NO TRADE explicit | PASS | PASS |
| Orchestrated agents and provider independence | Fixed roles, no agent broker credentials, deterministic execution boundary, default Codex runtime, explicit LiteLLM opt-in, same-runtime fallbacks, versioned I/O, and independent prompt resolution | PASS | PASS |
| Secure UI-first configuration | MFA, step-up, scoped vault references, masked secrets, execution-permission UI, visible durable kill switches, audit, and least privilege | PASS | PASS |
| Adapter boundaries and reconciliation | Capability-routed data/broker contracts separate economic identity from listings; execution commands are idempotent and actual reconciled broker state becomes authoritative | PASS | PASS |
| Auditability and controlled learning | Immutable Trade Plans, commands, journal events, version/evidence references, separated evidence classes, shared evaluator, staged promotion, and reproducibility metadata | PASS | PASS |

No constitutional exception is required. Phase 1 artifacts preserve every gate; implementation must
fail CI if contract, state-transition, authority-order, execution-permission, kill-switch,
idempotency, reconciliation, chart-read-only, evidence-class, or secret-redaction tests regress them.

## Project Structure

### Documentation (this feature)

```text
specs/001-matrades-product-platform/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   ├── events.md
│   ├── agent-contracts.md
│   └── adapter-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md                 # created later by $speckit-tasks
```

### Source Code (repository root)

```text
apps/
├── api/                     # FastAPI composition root and HTTP/SSE transport
├── worker/                  # Celery composition root and scheduled jobs
├── agent_worker/            # Codex App Server host; bounded agent execution
└── web/                     # Next.js operations and configuration UI

modules/
├── identity/                # auth, MFA, sessions, step-up
├── credentials/             # vault references, rotation, redaction
├── connections/             # provider registry and health
├── agents/                  # definitions, config, prompts, runtime, execution audit
├── accounts/                # trading accounts and consistent broker snapshots
├── prop_firms/              # firms, programs, rulesets, structured rules
├── policy/                  # deterministic eligibility and effective constraints
├── risk/                    # sizing, reserved/correlated/portfolio capacity
├── market_data/             # instruments, normalization, freshness, time series
├── analysis/                # indicators, structure, liquidity, regime, research
├── knowledge/               # source ingestion, authorization, contextual retrieval
├── strategies/              # lab, repository, compiler, similarity, lifecycle
├── backtesting/             # replay, costs, validation, paper trading
├── trading/                 # Trade Plans, autonomous lifecycle, reconciliation, monitoring
├── execution/               # permissions, kill switches, commands, broker-write authorization
├── journal/                 # live append-only observations and post-trade summaries
├── performance/             # evidence-class metrics, deterministic edge, health triggers
├── charts/                  # read-only chart queries and overlay projections
├── notifications/           # normalized notifications and channel dispatch
└── observability/           # audit, health, metrics, tracing

adapters/
├── agent_runtime/{codex_app_server,litellm}/
├── market_data/{twelve_data,coinbase,coingecko,broker_market_data}/
├── instrument_reference/    # venue listings, contract terms, chains, corporate actions
├── macro/{fred,cftc}/
├── calendar/
├── news/
├── broker/mt5_bridge/
├── embeddings/
├── blob_store/
└── notifications/

bridges/
└── mt5/                     # authenticated read/event/write bridge with local safety controls

packages/
├── contracts/               # versioned schemas and generated clients/types
├── strategy_sdk/            # declarative rule vocabulary and evaluator contract
├── broker_sdk/              # bridge/adapter schemas
└── shared/                  # identifiers, money/time primitives; no domain logic

infra/
├── compose/
├── migrations/
├── deployment/
└── observability/

tests/
├── unit/
├── property/
├── integration/
├── contract/
├── e2e/
├── replay/
├── security/
└── failure/
```

**Structure Decision**: Use a modular monolith so financial invariants and transactions remain
simple in V1 while Python domain packages enforce dependency rules. The API and workers compose the
same application modules; the web consumes generated OpenAPI/event contracts. The MT5 bridge is
separate because it may run beside MT5 on another operating system. Redis and LangGraph checkpoints
may accelerate work but cannot replace database-backed domain state. Dedicated agent-worker
containers launch pinned Codex App Server processes locally over stdio through the Python SDK;
LiteLLM is loaded only for explicitly assigned alternative profiles.

## Architectural Decisions

### Authority and state ownership

- PostgreSQL aggregates own configuration versions, autonomous workflow states, execution permission
  versions, account/platform kill switches, risk reservations, Trade Plans, execution commands,
  strategy lifecycle, reconciliation, journal events, and audit evidence.
- LangGraph coordinates bounded agent steps and may checkpoint resumable reasoning; application
  state machines validate every transition before and after an agent call.
- Celery executes ingestion, research, indexing, backtesting, notifications, and scheduled health
  work with idempotency keys and database-recorded job status.
- Agents receive immutable structured context and return schema-validated recommendations. They
  never mutate broker, policy, guardrail, account, strategy, permission, or kill-switch authority
  directly. Only the deterministic execution service may invoke broker-write adapter methods.

### Agent runtime routing

- `AgentRuntimeAdapter` is the only application-facing execution port. Runtime selection is
  resolved before model selection and is persisted with every configuration and execution.
- Every required agent resolves to `CODEX_APP_SERVER` unless that agent or its explicitly assigned
  model profile selects `LITELLM`. The Orchestrator's runtime choice does not silently migrate other
  agents to LiteLLM.
- Codex agent workers use the stable Python Codex SDK to control its pinned local App Server over
  stdio. V1 does not depend on the experimental remote WebSocket transport.
- Model fallback remains within the selected runtime. Exhausted Codex fallbacks produce the role's
  safe DEGRADED, BLOCKED, or unavailable result; routing never crosses to LiteLLM automatically.
- LiteLLM configuration, health, and model synchronization are available only when the optional
  adapter is enabled. Connecting LiteLLM does not reassign existing agents or profiles.

### Data and integration boundaries

- One market-data service owns provider connections, economic-asset identity, exact venue/broker
  listing mappings, contract-specification versions, validation, normalization, cache, and
  persistence. Agents never open provider streams.
- Connection capabilities are indexed by asset class, instrument type, venue, data capability, and
  account. A matrix cell resolves an authoritative research source and, before execution, an exact
  executable broker listing; no provider symbol or continuous future becomes a canonical trade ID.
- Structured application data, time-series observations, and semantic knowledge remain logically
  separated even when PostgreSQL hosts all three.
- Every input used for a material decision is referenced by immutable ID/version, source timestamp,
  recorded timestamp, freshness status, owner/account scope, and correlation ID.
- HTTP/OpenAPI handles commands and queries; SSE delivers UI operational updates; WebSocket is
  reserved for high-rate provider and MT5 bridge streams. All event consumers are idempotent and
  ordering-safe per aggregate.

### Instrument identity and daily matrix research

- `UnderlyingAsset` identifies the economic asset; `Instrument` identifies its asset class and
  spot/CFD/futures expression; `VenueInstrument` identifies the exact provider, broker, or exchange
  listing. Dated `FuturesContract` records are executable; `ContinuousFuture` series are analytical
  evidence only.
- Immutable effective-dated `InstrumentSpecificationVersion` records preserve contract multiplier,
  tick size/value, quantity unit and increment, currencies, session calendar, margin, financing,
  expiry/notice/roll terms, ownership or custody semantics, and source/freshness provenance.
- A scheduled account research run creates 12 `ResearchLaneResult` records keyed by
  `(asset_class, instrument_type)`. Each cell is idempotent, independently retryable, and ends with
  `READY` plus one candidate or an explicit `NO_TRADE`, `NOT_CONFIGURED`, `UNAVAILABLE`, `STALE`, or
  `BLOCKED` status; partial failure cannot be represented as a complete healthy matrix.
- `forex_research`, `metals_research`, `crypto_research`, and `stocks_research` each rank the three
  instrument types for their asset class. Cross-asset analyst roles and the critic retain bounded
  structured contracts; eligible lane results continue into analysis without an approval state.

### Contract and data migration

- Preserve existing category-only research runs, selections, proposals, approvals, and trades as immutable
  historical evidence tagged `LEGACY_UNTYPED`; do not guess whether an old symbol meant spot, CFD,
  or futures. Legacy approval records remain readable but cannot drive new transitions. Legacy
  untyped records cannot seed a new executable Trade Plan until an
  operator verifies the exact typed listing and specification.
- Introduce asset-class, instrument-type, lane, venue-listing, specification-version, and dated-
  contract columns as nullable in the expand migration; backfill only provable mappings; deploy
  dual-read compatibility; then require typed references for new writes before the contract
  migration is finalized. Rollback disables new typed writes without deleting typed evidence.
- Regenerate Python and TypeScript clients atomically from the revised OpenAPI contract. Workers
  reject unsupported contract/schema versions, and event consumers support the documented overlap
  window without treating a three-category legacy result as a complete 12-lane run.

### Instrument-type valuation and lifecycle

- Spot exposure uses native quantity and cash/underlying availability; CFD exposure uses broker lot
  size, contract multiplier, margin, financing, and cash-adjustment terms; futures P&L uses exact
  dated contracts, tick movement, tick value, margin, settlement, expiry, and roll eligibility.
- Notional, margin, and maximum loss are separate values. Sizing calculates loss per minimum
  quantity increment through the Stop Loss plus deterministic costs and gap allowance, rounds down,
  then recomputes risk, margin, and aggregate exposure. Missing required metadata blocks execution.
- Shared-underlying exposure aggregates across wrappers: spot gold, gold CFD, and gold futures are
  correlated economic exposure, not independent diversification.
- Futures rolls are explicit new Trade Plans and transactions; no position silently moves to another
  contract. Stock corporate actions and CFD cash adjustments are point-in-time events;
  raw/as-traded and adjusted analytical series remain distinct.

### Risk concurrency and conservative defaults

- Executable Trade Plans atomically reserve candidate worst-case risk before command authorization.
  Block, invalidation, expiry, command rejection, or cancellation releases it; broker acceptance keeps
  it reserved, and confirmed fills convert it to actual open-position reserved risk. Partial fills
  split reservation between filled position risk and unfilled command risk.
- A missing or invalid Stop Loss is unbounded risk and blocks a new Trade Plan unless an explicit
  deterministic account/strategy rule supplies a compliant protective bound.
- Dynamic additional-trade capacity is candidate-dependent. The dashboard shows remaining risk
  budget and labels any integer capacity with the configured standard candidate-risk unit; each real
  Trade Plan is recalculated independently.
- Correlation risk uses configured exposure groups plus rolling return correlation where sufficient
  data exists. The more conservative result governs; missing evidence falls back to the configured
  group cap or blocks when no safe bound exists.
- Every result pins the exact venue instrument and specification version used. Margin availability
  never substitutes for worst-case-loss capacity, and a specification change, expiry threshold,
  corporate action, financing change, or stale mapping triggers revalidation.

### Deterministic execution, permissions, and kill switches

- `ExecutionPermissionProfile` is versioned per account and independently controls `NEW_ENTRY`,
  `ORDER_CANCELLATION`, `STOP_LOSS_CREATE_OR_MODIFY`, `TAKE_PROFIT_CREATE_OR_MODIFY`,
  `PARTIAL_CLOSE`, and `FULL_EXIT`.
  Connections remain read-only until an active profile enables the requested action and the adapter
  declares that capability. Permission changes require step-up authentication and append audit events.
- Durable `KillSwitch` aggregates exist for the platform and each account. Activation is fail-closed,
  immediately visible, survives restart, and prevents authorization of new entries and discretionary
  writes. It does not remove broker-hosted protections. Deactivation requires step-up authentication,
  a fresh broker/account health check, and an audited configuration command; no agent can operate it.
- A versioned `TradePlan` is immutable once execution begins. `ExecutionCommand` is the sole broker-
  write unit and stores action, requested values, Trade Plan or management-decision reference,
  permission/policy/risk/account snapshots, deterministic authorization digest, idempotency key,
  expected aggregate version, expiry, and correlation/causation IDs.
- Command authorization and outbox insertion occur in one database transaction after re-reading
  current permissions, kill switches, authoritative broker state, data freshness, policy, and risk.
  The bridge accepts a command only when its signed account scope, action capability, command identity,
  and expiry are valid. Agents emit bounded recommendations; they cannot invoke the adapter directly.
- Command states are `CREATED -> VALIDATING -> BLOCKED|AUTHORIZED -> QUEUED -> DISPATCHING ->
  ACKNOWLEDGED|REJECTED|OUTCOME_UNKNOWN`, with `PARTIALLY_APPLIED`, `APPLIED`, `SUPERSEDED`, and
  reconciliation outcomes representing post-dispatch truth. Timeout or transport loss after dispatch
  becomes `OUTCOME_UNKNOWN`; Matrades queries broker orders,
  positions, and deal history before any retry. A retry reuses the command identity and never creates
  a second economic intent.
- Protection changes, partial closes, and full exits use the same command pipeline. A risk-reducing
  action may proceed under a policy-defined degraded-data rule only when broker state is fresh enough
  to identify the exact position and the action cannot increase exposure. Entry and risk-increasing
  changes always fail closed.

### Live trade experience, journaling, knowledge, and analytics

- Each active-position projection joins the immutable Trade Plan, actual broker order/fill/position,
  current protections and P&L, permission and kill-switch state, monitoring decisions, and source
  freshness. A read-only chart query supplies live/historical candles and overlays for plan levels,
  fills, protections, partial/full exits, journal events, and automated actions. Chart UI components
  receive no command schema, broker credential, or execution endpoint.
- The Journal agent appends immutable `LiveJournalObservation` records for material market, account,
  risk, strategy, execution, and position-state events. Structured references and source times are
  authoritative; agent prose is labeled observation versus inference. A terminal trade produces one
  `PostTradeSummary` citing the underlying event range.
- A transactional outbox queues each committed journal event for owner-scoped chunking and pgvector
  indexing. Index lag or failure changes only `KnowledgeIndexStatus`; it never changes the journal.
  `knowledge_assistant` retrieves authorized knowledge and journal segments, cites every material
  factual claim, labels active-trade values as historical unless refreshed from structured services,
  and has no Trade Plan or execution tool.
- `PerformanceObservation` is tagged exactly `BACKTEST`, `PAPER`, or `LIVE`. Versioned deterministic
  calculators produce separate metric sets and side-by-side comparisons; operational views default
  to `LIVE`. Edge is after-cost expectancy with formula, population, period, sample size, uncertainty,
  and `POSITIVE`, `INCONCLUSIVE`, or `NEGATIVE` status. Aggregates drill down to contributing trades;
  open-position unrealized P&L remains separate.
- Broker acceptance/fill events drive a notification outbox keyed by `(execution_command_id,
  notification_kind, fill_revision, channel)`. Unconfirmed submissions are never labeled entered;
  partial and complete fills update the same execution timeline without duplicate entry alerts.

### Strategy integrity

- Draft conversation is contextual, never canonical. Accepted rule revisions form the draft;
  canonicalization precedes exact hashing, structural/parameter comparison, semantic candidate
  retrieval, and behavioral comparison.
- Exact duplicates cannot create a second permanent identity. Active versions are immutable, and
  improvements branch to new drafts.
- One compiler/evaluator contract serves backtesting, paper trading, and live setup detection.
  Arbitrary generated code is never activated.
- Validation is profile-specific by asset class, instrument type, listing, contract specification,
  cost model, calendar, lifecycle rules, and account compatibility. Spot validation cannot be
  silently reused for CFDs or futures.
- `DRAFT -> SPECIFIED -> IMPLEMENTED -> BACKTESTING -> VALIDATING -> PAPER_TRADING -> APPROVED ->
  ACTIVE` is the promotion path; `DEGRADED`, `SUSPENDED`, and `RETIRED` are explicit post-promotion
  health states.

## Implementation Sequence

### Stage 0 - Contracts and invariants

Freeze asset-class and instrument-type enums, research-lane keys, underlying/listing/contract IDs,
instrument-specification versions, money/quantity/time units, ownership rules, error format, event
envelope, Trade Plan and execution-command actions/state machines, per-account permission actions,
kill-switch semantics, freshness, idempotency, optimistic concurrency, legacy-read/new-write migration
compatibility, and adapter/agent contracts. Build authority-order, forbidden-dependency, and no-agent-
broker-write architecture tests first.

### Stage 1 - Platform and security foundation

Create the monorepo, database migrations, queue, API/web shells, authentication, email verification,
TOTP MFA, recovery codes, sessions, step-up authentication, credential vault abstraction, audit
events, health registry, and baseline observability. Audit capture starts here and expands with every
stage.

### Stage 2 - Configuration and agent runtime

Implement the Codex App Server worker pool and default runtime adapter first, then the optional
LiteLLM adapter and explicit selection UI. Add the model catalog, runtime-bound profiles and
fallbacks, all 17 fixed agent definitions including `stocks_research` and `knowledge_assistant`, agent configuration versions,
independent system/user prompt resolution, tool permission sets, capability validation, test-agent
flow, and execution audit. Seed the knowledge-source registry but do not permit retrieval to affect
authority.

### Stage 3 - Accounts, policy, and risk

Implement accounts, prop-firm hierarchy and versioned rules, guardrails, consistent account
snapshots, effective limits, money/currency conversion, high-water/daily drawdown, reserved risk,
correlation/exposure groups, candidate reservations, dynamic capacity, and instrument-type-dispatched
valuation and sizing. Include cash availability, contract multiplier, tick/point value, quantity
increment, margin, financing/funding, expiry/roll, gap allowance, currency conversion, and shared-
underlying aggregation in deterministic hard-block explanations. Complete boundary/property and
concurrency tests before executable Trade Plans.

### Stage 4 - Market, event, and knowledge data

Implement underlying assets, typed instruments, exact venue/broker listings, aliases, immutable
specification versions, provider capability/binding registry, broker symbol synchronization,
futures chains and roll rules, calendars, corporate actions, financing/funding observations, and
point-in-time universe membership. Extend Twelve Data, Coinbase, CoinGecko, broker-market-data,
FRED, CFTC, calendar, and news adapters through capability contracts; share provider source cuts
across account schedules with quota-aware batching, freshness, and reconnection. Coinbase remains a
configured exchange feed and CoinGecko broad discovery context; neither is silently promoted to an
unsupported lane authority. Complete knowledge ingestion, provenance, scoping, retrieval, and
degraded behavior behind the structured-data boundary.

### Stage 5 - Autonomous analysis and market research

Build deterministic indicators, structure, liquidity, volatility, correlation, and fingerprints;
bounded fundamental/sentiment/regime outputs; 12 independently terminal daily lane rankings;
asset-class specialist review; exact typed candidate and exclusion evidence; autonomous candidate
progression without selection approval; deterministic next-candidate fallback after invalidation; and
explicit READY, NO TRADE, NOT CONFIGURED, UNAVAILABLE, STALE, BLOCKED, and aggregate degraded paths.

### Stage 6 - Strategy platform and validation

Build taxonomy, patterns, repository, drafts, immutable rule provenance, family-aware completeness,
Strategy Assistant suggestions/change sets, canonicalization, similarity, comparison UI, shared
compiler/evaluator, historical replay and costs, out-of-sample/walk-forward/stress/Monte Carlo,
account-policy simulation, paper trading, promotion, and origin-neutral selection.
Validation profiles pin instrument type, exact listing/contract, specification version, calendar,
point-in-time constituents, corporate actions, financing/funding, futures chain/roll, costs, and
rounding. Continuous futures may supply analysis but dated contracts supply fills and P&L.
Strategy generation first resolves an immutable approved-market evidence pack, summarizes only a
chronological discovery partition for the agent, generates multiple cited hypotheses, and uses a
deterministic unseen holdout partition to select or safely reject them before human approval. This
preliminary screen is research evidence and never substitutes for formal validation or paper trading.

### Stage 7 - Trade Plan and deterministic execution authorization

Implement strategy selection, setup detection, immutable Trade Plan construction, fresh snapshot
capture, policy/effective-limit/portfolio/risk evaluation, PASS/REDUCE SIZE/HARD BLOCK, critic review,
candidate reservation, per-account execution permission profiles, durable account/platform kill
switches, command authorization, transactional outbox, and the automation operations view. Validate
all FR-032 fields, the 5-second evaluation target, and that disabled or blocked actions emit no broker write.

### Stage 8 - Execution-capable broker bridge and reconciliation

Extend the authenticated MT5/Wine bridge with capability negotiation and bounded order entry,
cancellation, protection change, partial-close, and full-exit commands. Matrades enqueues commands in
the durable Python bridge; the MQL5 EA polls them through outbound `WebRequest`, submits validated
`MqlTradeRequest` operations, and posts receipts/results/events. Implement signed command envelopes,
transactional bridge leasing and a restart-safe local ledger, expiry, nonce/idempotency persistence,
symbol and position preconditions, broker snapshots, orders/deals/positions, exact typed instrument/
contract matching, partial fills, uncertain-outcome reconciliation before retry, duplicate/out-of-
order event handling, and conversion from planned to actual broker authority. Ambiguous matches
become BLOCKED rather than waiting for routine approval.

### Stage 9 - Autonomous monitoring, charts, and live journaling

Implement live position analysis, management-policy/risk/permission revalidation, HOLD and structured
position-change actions through the execution service, broker protection events, safe disconnect/
reconnect behavior, adjacent active Trade Plans, read-only interactive charts and overlays, immutable
live Journal-agent observations, continuous knowledge indexing, and terminal post-trade summaries.

### Stage 10 - Knowledge Q&A, analytics, notifications, and hardening

Implement the read-only citation-grounded Knowledge Assistant; separate `BACKTEST`, `PAPER`, and
`LIVE` performance projections; deterministic win/loss, profitability, drawdown, expectancy, and edge
calculations with drill-down; deduplicated confirmed-entry notifications in-product and through
Telegram/Pushover adapters; strategy health and controlled research triggers; automation dashboards;
backup/restore; security review; load/replay tests; execution failure simulations; source/license
review; and production runbooks.

## Verification Strategy

- Unit and property tests cover financial arithmetic, strictest-limit monotonicity, safe rounding,
  drawdown bases, reset boundaries, reserved/correlated risk, prompt/model resolution, and lifecycle
  transition guards. Type-specific properties cover spot cash/quantity, CFD multiplier/financing,
  futures tick/expiry/roll, and shared-underlying exposure across wrappers.
- Adapter contract tests run against provider fixtures and sandboxes for normalization, health,
  freshness, reconnection, rate limits, duplicate/out-of-order events, and redaction.
- Matrix contract/replay tests require 12 terminal lane results, isolate missing/stale bindings,
  reject symbol-only and cross-type substitution, prove shared source-cut quota behavior, and ensure
  continuous futures never become actionable.
- Integration tests cover persistence, migrations, task idempotency, consistent account snapshots,
  concurrent Trade Plan reservations, permission and kill-switch races, Codex App Server process
  recovery, same-runtime fallback, explicit LiteLLM selection, prohibition of cross-runtime fallback,
  knowledge isolation, bridge authentication, command idempotency, partial fills, uncertain-outcome
  reconciliation, and immutable audit linkage.
- Replay tests prove point-in-time market/macro handling, no look-ahead, shared-evaluator parity,
  realistic trading costs, and reproducible strategy/policy/risk outcomes.
- Security tests cover tenant isolation, MFA/step-up, session revocation, secret rotation/redaction,
  authorization, prompt injection boundaries, runtime-selection authorization, no silent runtime
  migration, agent tool-permission invariance, no agent broker credentials, chart read-only behavior,
  Knowledge Assistant execution refusal, and step-up-protected permission/kill-switch changes.
- End-to-end tests cover autonomous 12-lane progression, NO TRADE, hard block, reduced size, enabled
  and disabled account actions, kill switches, entry/cancel/protection/partial/full-exit execution,
  partial fills, ambiguous/unknown reconciliation, protective closure, active Trade Plan and chart
  overlays, live journal indexing, grounded Q&A refusal, separate analytics populations, confirmed-
  entry notifications, both AI strategy origins, and retrieval failure.
- Acceptance suites map SC-001 through SC-024 directly and publish evidence for release gates.

## Complexity Tracking

No constitutional violation requires a complexity exception. The modular monolith, PostgreSQL
extensions, one task queue, and limited deployment boundaries are the simplest design that preserves
transactional financial invariants, durable autonomous execution state, time-series analysis,
contextual retrieval, read-only charts, and cross-platform MT5 operation.
