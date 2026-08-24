# Implementation Plan: Matrades Product Platform

**Branch**: `001-matrades-product-platform` | **Date**: 2026-08-24 |
**Spec**: [spec.md](./spec.md)

**Input**: Consolidated feature specification from
`specs/001-matrades-product-platform/spec.md`, informed by the three supplied implementation
plans and governed by Matrades Constitution 1.3.0.

## Summary

Build Matrades V1 as a browser-based decision-support platform backed by a Python modular
monolith, durable background workers, a separately deployable read-only MT5 bridge, and a
TypeScript web application. PostgreSQL is the authority for configuration, workflow, policy,
risk, strategies, approvals, trades, and audit evidence; TimescaleDB and pgvector extend the
same data platform for time-series and contextual knowledge, while Redis remains non-authoritative.

The design enforces hard financial rules in deterministic services, persists all three human
approval gates as explicit state machines, compiles declarative strategy rules into one shared
backtest/paper/live evaluator, and bounds AI agents behind versioned contracts, independent prompt
resolution, least-privilege tools, and a default Codex App Server runtime pool. LiteLLM remains an
explicit per-agent or per-profile alternative and is never an automatic cross-runtime fallback.
Coinbase replaces Binance as the required V1 crypto exchange-data provider, `strategy_assistant`
completes the 15-agent registry, and contextual knowledge is isolated from authoritative market,
account, policy, and risk state.

## Technical Context

**Language/Version**: Python 3.13 for backend, workers, deterministic engines, and research;
TypeScript 5.x on Node.js 24 LTS for the web application; declarative JSON/YAML for strategy and
contract artifacts

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy, Alembic; Celery 5.6 with Redis transport;
LangGraph for bounded workflow orchestration only; the stable `openai-codex` Python SDK with its
pinned Codex CLI/App Server runtime; optional LiteLLM Proxy; NumPy, Polars/pandas, SciPy, and
vectorbt where appropriate for research; Next.js 16 LTS, React, Tailwind CSS, accessible UI
primitives, and TanStack Query

**Storage**: PostgreSQL 17 as system of record with compatible TimescaleDB and pgvector extensions;
Redis for cache, rate limits, locks, and task transport only; uploaded source documents and large
artifacts use an access-controlled blob abstraction when database storage is unsuitable

**Testing**: pytest, pytest-asyncio, Hypothesis, and integration containers for Python; Vitest and
Testing Library for TypeScript; Playwright for browser journeys; OpenAPI/schema and adapter contract
tests; deterministic replay, failure injection, and migration tests

**Target Platform**: Linux containers for API, background workers, Codex agent workers, web,
database, and Redis; optional separately enabled LiteLLM Proxy containers; evergreen desktop
browsers; an authenticated MT5 bridge runnable on Windows, macOS/Wine, or a hosted Windows
environment

**Project Type**: Full-stack web application in a monorepo, delivered as a modular monolith plus
workers and a separately deployable broker bridge

**Performance Goals**: At least 95% of complete candidate evaluations return a decision or explicit
safe-failure status within 5 seconds after inputs are available; at least 95% of daily research runs
produce HIL-1 results or a safe-failure status within 10 minutes; operational state changes reach
the UI within 2 seconds under normal conditions

**Constraints**: Manual execution only; no default broker writes; current account equity and
consistent snapshots required before HIL-2; strictest applicable constraint wins; hard-blocked
candidates never enter an actionable approval queue; secrets never enter prompts, logs, or client
responses; RAG is non-authoritative; every required agent defaults to the Codex App Server runtime;
LiteLLM requires an explicit per-agent or per-profile selection and cannot be an automatic fallback;
PostgreSQL, not Redis or an agent checkpoint alone, owns durable workflow and approval state; all
timestamps are stored in UTC with source timezone metadata

**Scale/Scope**: V1 supports individual authenticated traders with multiple personal or prop-firm
accounts, the 15 required logical agents, one normal active instrument per market category, multiple
provider connections, long-running research/backtest jobs, and event-driven monitoring. Module and
adapter boundaries permit later multi-user and service extraction without adding V1 microservices.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Constitutional gate | Design evidence | Pre-design | Post-design |
|---|---|---|---|
| Ordered authority and deterministic safety | Policy, effective-limit, risk, portfolio, and strategy evaluators are deterministic and precede critic/HIL | PASS | PASS |
| Three HIL gates and manual execution | Persisted HIL-specific actions; TAKE only reserves and awaits manual entry; broker adapter is read-only | PASS | PASS |
| Account-aware risk and prop compliance | Immutable account snapshots, versioned rulesets, reserved risk, candidate reservations, and correlated exposure | PASS | PASS |
| Equal strategy validation | Four origins converge on one canonicalization, implementation, validation, paper, and promotion pipeline | PASS | PASS |
| Authoritative data and bounded RAG | Retrieval router and contracts prevent knowledge output from supplying current facts, policy, or risk | PASS | PASS |
| Safe failure and NO TRADE | Health/freshness states and circuit breakers make BLOCK, DEGRADED, WAIT, and NO TRADE explicit | PASS | PASS |
| Orchestrated agents and provider independence | Fixed roles, a default Codex runtime adapter, explicit LiteLLM opt-in, same-runtime fallbacks, versioned I/O, and independent prompt resolution | PASS | PASS |
| Secure UI-first configuration | MFA, step-up, scoped vault references, masked secrets, audit, and configuration APIs/UI | PASS | PASS |
| Adapter boundaries and reconciliation | Provider-neutral data/broker contracts; actual reconciled broker state becomes authoritative | PASS | PASS |
| Auditability and controlled learning | Immutable version/evidence references, shared evaluator, staged promotion, and reproducibility metadata | PASS | PASS |

No constitutional exception is required. Phase 1 artifacts preserve every gate; implementation must
fail CI if contract, state-transition, authority-order, or secret-redaction tests regress them.

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
├── trading/                 # proposals, HIL state machines, reconciliation, monitoring
├── journal/                 # append-oriented trade and decision evidence
├── performance/             # metrics, health, controlled research triggers
├── notifications/           # normalized notifications and channel dispatch
└── observability/           # audit, health, metrics, tracing

adapters/
├── agent_runtime/{codex_app_server,litellm}/
├── market_data/{twelve_data,coinbase,coingecko}/
├── macro/{fred,cftc}/
├── calendar/
├── news/
├── broker/mt5_bridge/
├── embeddings/
├── blob_store/
└── notifications/

bridges/
└── mt5/                     # independent authenticated read/event bridge

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

- PostgreSQL aggregates own configuration versions, workflow states, approvals, risk reservations,
  strategy lifecycle, reconciliation, and audit evidence.
- LangGraph coordinates bounded agent steps and may checkpoint resumable reasoning; application
  state machines validate every transition before and after an agent call.
- Celery executes ingestion, research, indexing, backtesting, notifications, and scheduled health
  work with idempotency keys and database-recorded job status.
- Agents receive immutable structured context and return schema-validated recommendations. They
  never mutate broker, policy, guardrail, account, strategy, or approval authority directly.

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

- One market-data service owns provider connections, canonical instrument mapping, validation,
  normalization, cache, and persistence. Agents never open provider streams.
- Structured application data, time-series observations, and semantic knowledge remain logically
  separated even when PostgreSQL hosts all three.
- Every input used for a material decision is referenced by immutable ID/version, source timestamp,
  recorded timestamp, freshness status, owner/account scope, and correlation ID.
- HTTP/OpenAPI handles commands and queries; SSE delivers UI operational updates; WebSocket is
  reserved for high-rate provider and MT5 bridge streams. All event consumers are idempotent and
  ordering-safe per aggregate.

### Risk concurrency and conservative defaults

- Actionable proposals atomically reserve candidate worst-case risk. WAIT, REJECT, expiry, or
  cancellation releases it; TAKE carries the reservation into awaiting manual entry; reconciliation
  converts it to actual open-position reserved risk.
- A missing or invalid Stop Loss is unbounded risk and blocks a new proposal unless an explicit
  deterministic account/strategy rule supplies a compliant protective bound.
- Dynamic additional-trade capacity is candidate-dependent. The dashboard shows remaining risk
  budget and labels any integer capacity with the configured standard candidate-risk unit; each real
  proposal is recalculated independently.
- Correlation risk uses configured exposure groups plus rolling return correlation where sufficient
  data exists. The more conservative result governs; missing evidence falls back to the configured
  group cap or blocks when no safe bound exists.

### Strategy integrity

- Draft conversation is contextual, never canonical. Accepted rule revisions form the draft;
  canonicalization precedes exact hashing, structural/parameter comparison, semantic candidate
  retrieval, and behavioral comparison.
- Exact duplicates cannot create a second permanent identity. Active versions are immutable, and
  improvements branch to new drafts.
- One compiler/evaluator contract serves backtesting, paper trading, and live setup detection.
  Arbitrary generated code is never activated.
- `DRAFT -> SPECIFIED -> IMPLEMENTED -> BACKTESTING -> VALIDATING -> PAPER_TRADING -> APPROVED ->
  ACTIVE` is the promotion path; `DEGRADED`, `SUSPENDED`, and `RETIRED` are explicit post-promotion
  health states.

## Implementation Sequence

### Stage 0 - Contracts and invariants

Freeze identifiers, money/time units, ownership rules, error format, event envelope, HIL-specific
actions, state machines, freshness semantics, idempotency, optimistic concurrency, and adapter/agent
contracts. Build authority-order and forbidden-dependency architecture tests first.

### Stage 1 - Platform and security foundation

Create the monorepo, database migrations, queue, API/web shells, authentication, email verification,
TOTP MFA, recovery codes, sessions, step-up authentication, credential vault abstraction, audit
events, health registry, and baseline observability. Audit capture starts here and expands with every
stage.

### Stage 2 - Configuration and agent runtime

Implement the Codex App Server worker pool and default runtime adapter first, then the optional
LiteLLM adapter and explicit selection UI. Add the model catalog, runtime-bound profiles and
fallbacks, all 15 fixed agent definitions, agent configuration versions, independent system/user
prompt resolution, tool permission sets, capability validation, test-agent flow, and execution
audit. Seed the knowledge-source registry but do not permit retrieval to affect authority.

### Stage 3 - Accounts, policy, and risk

Implement accounts, prop-firm hierarchy and versioned rules, guardrails, consistent account
snapshots, effective limits, money/currency conversion, high-water/daily drawdown, reserved risk,
correlation/exposure groups, candidate reservations, dynamic capacity, deterministic sizing, and
hard-block explanations. Complete boundary/property and concurrency tests before trade proposals.

### Stage 4 - Market, event, and knowledge data

Implement canonical instruments and aliases; Twelve Data, Coinbase, CoinGecko, FRED, CFTC, calendar,
and news adapters; normalized time-series storage; freshness and reconnection; knowledge ingestion,
provenance, owner scoping, hybrid retrieval, and degraded behavior. Coinbase is the V1 exchange feed;
CoinGecko remains broad research context.

### Stage 5 - Analysis, research, and HIL-1

Build deterministic indicators, structure, liquidity, volatility, correlation, and fingerprints;
bounded fundamental/sentiment/regime outputs; daily cross-market ranking; persisted selections;
APPROVE, REPLACE, and RERUN RESEARCH actions; and NO TRADE/degraded paths.

### Stage 6 - Strategy platform and validation

Build taxonomy, patterns, repository, drafts, immutable rule provenance, family-aware completeness,
Strategy Assistant suggestions/change sets, canonicalization, similarity, comparison UI, shared
compiler/evaluator, historical replay and costs, out-of-sample/walk-forward/stress/Monte Carlo,
account-policy simulation, paper trading, promotion, and origin-neutral selection.

### Stage 7 - Proposal vertical slice and HIL-2

Implement strategy selection, setup detection, deterministic construction, fresh snapshot capture,
policy/effective-limit/portfolio/risk evaluation, PASS/REDUCE SIZE/HARD BLOCK, critic review,
candidate reservation, Trade Desk, and TAKE/WAIT/REJECT. Validate all FR-032 fields and the 5-second
acceptance target.

### Stage 8 - Broker bridge and reconciliation

Implement authenticated MT5/Wine bridge health and read/event contracts, broker snapshots and
positions, awaiting-manual-entry state, deterministic matching, ambiguous user confirmation, event
deduplication/order handling, and conversion from proposal values to actual broker authority.

### Stage 9 - Monitoring and HIL-3

Implement live position analysis, management-policy/risk validation, HOLD and position-change
recommendations, APPROVE/WAIT/REJECT, manual-change reconciliation, broker protection events, and
safe disconnect/reconnect behavior.

### Stage 10 - Closed loop and hardening

Complete journal timelines, structured performance, strategy health, controlled research triggers,
approval inbox, dashboards, in-app notifications followed by optional channels, backup/restore,
security review, load/replay tests, failure simulations, source/license review, and production runbooks.

## Verification Strategy

- Unit and property tests cover financial arithmetic, strictest-limit monotonicity, safe rounding,
  drawdown bases, reset boundaries, reserved/correlated risk, prompt/model resolution, and lifecycle
  transition guards.
- Adapter contract tests run against provider fixtures and sandboxes for normalization, health,
  freshness, reconnection, rate limits, duplicate/out-of-order events, and redaction.
- Integration tests cover persistence, migrations, task idempotency, consistent account snapshots,
  concurrent proposal reservations, Codex App Server process recovery, same-runtime fallback,
  explicit LiteLLM selection, prohibition of cross-runtime fallback, knowledge isolation, bridge
  authentication, reconciliation, and immutable audit linkage.
- Replay tests prove point-in-time market/macro handling, no look-ahead, shared-evaluator parity,
  realistic trading costs, and reproducible strategy/policy/risk outcomes.
- Security tests cover tenant isolation, MFA/step-up, session revocation, secret rotation/redaction,
  authorization, prompt injection boundaries, runtime-selection authorization, no silent runtime
  migration, and agent tool-permission invariance.
- End-to-end tests cover all actions at HIL-1/2/3, NO TRADE, hard block, reduced size, manual entry,
  ambiguous reconciliation, protective closure, all four strategy origins, and retrieval failure.
- Acceptance suites map SC-001 through SC-015 directly and publish evidence for release gates.

## Complexity Tracking

No constitutional violation requires a complexity exception. The modular monolith, PostgreSQL
extensions, one task queue, and limited deployment boundaries are the simplest design that preserves
durable HIL workflows, time-series analysis, contextual retrieval, and cross-platform MT5 operation.
