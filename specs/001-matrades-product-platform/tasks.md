# Tasks: Matrades Product Platform

**Input**: Design documents from `/specs/001-matrades-product-platform/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and `.specify/memory/constitution.md`

**Tests**: Tests are required because the specification, plan, and constitution make deterministic safety, contract, replay, security, failure, and end-to-end evidence release gates.

**Organization**: Tasks are grouped by user story. Tasks in a story phase carry that story's label; shared setup, blocking foundation, and cross-cutting release work do not.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and does not depend on incomplete work
- **[Story]**: Maps the task to a user story in `spec.md`
- Every task names an exact implementation or test path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the planned monorepo, toolchains, local services, and contract generation.

- [X] T001 Create the planned source and test directory tree with package markers in `apps/api/app/__init__.py`, `apps/worker/app/__init__.py`, `apps/agent_worker/app/__init__.py`, `modules/__init__.py`, `adapters/__init__.py`, and `tests/__init__.py`
- [X] T002 Configure the Python 3.13 workspace with pinned backend, worker, data, AI, test, and stable `openai-codex` SDK dependencies in `pyproject.toml`
- [X] T003 [P] Configure the Node 24 workspace, shared scripts, and package manager constraints in `package.json`
- [X] T004 [P] Scaffold the FastAPI composition root and version endpoint in `apps/api/app/main.py`
- [X] T005 [P] Scaffold the Celery composition root and Codex agent-worker process host in `apps/worker/app/celery_app.py` and `apps/agent_worker/app/main.py`
- [X] T006 [P] Scaffold the Next.js 16 application, Tailwind theme, and accessible root layout in `apps/web/src/app/layout.tsx`
- [X] T007 Configure PostgreSQL 17, Redis, API, background worker, Codex agent worker, and web services with LiteLLM behind an optional profile in `infra/compose/compose.yaml`
- [X] T008 Enable TimescaleDB and pgvector and verify extension availability in `infra/migrations/versions/0001_enable_extensions.py`
- [X] T009 [P] Add typed environment loading, secret-safe validation, and development defaults in `packages/shared/config.py`
- [X] T010 [P] Configure Ruff, mypy, import boundaries, and pytest defaults in `pyproject.toml`
- [X] T011 [P] Configure ESLint, TypeScript strict mode, Vitest, and Playwright in `apps/web/package.json`
- [X] T012 Generate versioned Python and TypeScript API/event schemas from `specs/001-matrades-product-platform/contracts/openapi.yaml` into `packages/contracts/generated/`
- [X] T013 [P] Add local bootstrap, migration, seed, test, and contract-check commands in `Makefile`
- [X] T014 [P] Add CI jobs for lint, type checks, migrations, unit, property, integration, agent-runtime contract, security, and web tests in `.github/workflows/ci.yml`

**Checkpoint**: The API, workers including the Codex agent worker, web app, PostgreSQL extensions, Redis, migrations, and contract generation boot locally while LiteLLM remains disabled by default.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement durable state, transaction, event, authorization, adapter, health, and safe-failure primitives required by every story.

**Critical**: No user story implementation starts until this phase passes its contract and architecture checks.

- [X] T015 Implement UUID identifiers, UTC/source-time metadata, decimal money, quantity, and percentage primitives in `packages/shared/domain_types.py`
- [X] T016 [P] Implement SQLAlchemy engine, async sessions, and transaction-scoped unit-of-work support in `packages/shared/database.py`
- [X] T017 [P] Implement consistent machine-readable errors and FastAPI exception translation in `apps/api/app/errors.py`
- [X] T018 Create declarative metadata, naming conventions, optimistic version fields, and immutable timestamp mixins in `packages/shared/persistence.py`
- [X] T019 Implement the durable event envelope and serialization rules from `contracts/events.md` in `packages/contracts/events.py`
- [X] T020 Implement transactional outbox persistence and publication state in `packages/shared/outbox.py`
- [X] T021 Implement idempotency keys, request replay protection, and command deduplication in `packages/shared/idempotency.py`
- [X] T022 Implement append-only audit event persistence with actor and correlation metadata in `modules/observability/audit.py`
- [X] T023 [P] Implement authenticated actor, owner scope, and role authorization interfaces in `modules/identity/authorization.py`
- [X] T024 Integrate owner-scoped request context and authorization dependencies in `apps/api/app/dependencies.py`
- [X] T025 [P] Implement Celery task envelopes, retries, deduplication, cancellation, progress, and durable job-state hooks in `apps/worker/app/tasks/base.py`
- [X] T026 [P] Implement Redis cache, distributed-lock, rate-limit, and non-authoritative-state wrappers in `packages/shared/redis.py`
- [X] T027 Implement the provider-neutral adapter error, timeout, retry, freshness, and health contract in `adapters/base.py`
- [X] T028 Implement closed-by-default circuit breakers and safe degradation policies in `modules/connections/circuit_breaker.py`
- [X] T029 [P] Implement the access-controlled blob-store interface and local development adapter in `adapters/blob_store/local.py`
- [X] T030 [P] Implement centralized secret and sensitive-field redaction for logs, API payloads, and prompts in `modules/credentials/redaction.py`
- [X] T031 Implement server-sent event projection from the durable outbox without making the stream authoritative in `apps/api/app/routes/events.py`
- [X] T032 Implement component health, freshness, last-success, and error-state aggregation in `modules/observability/health.py`
- [X] T033 Add architecture, migration, event-envelope, idempotency, redaction, and Redis-authority tests in `tests/contract/test_foundation_invariants.py`

**Checkpoint**: Durable state and events are PostgreSQL-backed, owner-scoped, idempotent, observable, and fail closed where authority is unavailable.

---

## Phase 3: User Story 1 - Make a Safe Trade Decision (Priority: P1) - MVP

**Goal**: Turn current authoritative account, market, policy, and strategy evidence into PASS, REDUCE SIZE, or HARD BLOCK and expose only compliant proposals at HIL-2.

**Independent Test**: With seeded account, market, strategy, and policy fixtures, a compliant candidate reaches HIL-2 with the complete equity snapshot, an oversize candidate is reduced to a compliant size, and a hard-limit breach never enters the actionable queue.

### Tests for User Story 1

- [X] T034 [P] [US1] Add property tests for drawdown, reserved risk, strictest-limit selection, and non-increasing capacity in `tests/property/test_risk_invariants.py`
- [X] T035 [P] [US1] Add unit tests for money conversion, pip/tick value, contract size, rounding, and conservative price selection in `tests/unit/risk/test_financial_math.py`
- [X] T036 [P] [US1] Add risk evaluation API contract tests for PASS, REDUCE_SIZE, HARD_BLOCK, and stale input in `tests/contract/test_risk_api.py`
- [X] T037 [P] [US1] Add HIL-2 proposal and decision state-machine contract tests in `tests/contract/test_hil2_contract.py`
- [X] T038 [P] [US1] Add integration tests for concurrent candidate reservations and oversubscription prevention in `tests/integration/test_risk_reservation_concurrency.py`
- [X] T039 [P] [US1] Add replay tests proving identical snapshots and versions reproduce the same risk result in `tests/replay/test_pretrade_reproducibility.py`
- [X] T040 [P] [US1] Add browser tests for proposal evidence, reduce-size explanations, and hard-block visibility in `tests/e2e/test_safe_trade_decision.py`

### Implementation for User Story 1

- [X] T041 [P] [US1] Implement trading account and immutable account snapshot entities in `modules/accounts/models.py`
- [X] T042 [P] [US1] Implement effective constraint and policy evaluation entities in `modules/policy/models.py`
- [X] T043 [P] [US1] Implement position reservation, exposure group, correlation rule, and risk context entities in `modules/risk/models.py`
- [X] T044 [P] [US1] Implement trade proposal, approval request, and approval decision entities and HIL-2 transitions in `modules/trading/models.py`
- [X] T045 [US1] Add account, policy, risk, proposal, and approval tables and concurrency constraints in `infra/migrations/versions/0002_pretrade_core.py`
- [X] T046 [P] [US1] Implement consistent broker snapshot validation, current-equity requirements, and stale/mismatch blocking in `modules/accounts/snapshots.py`
- [X] T047 [P] [US1] Implement strictest-applicable-constraint resolution with source, version, reason, and enforcement level in `modules/policy/effective_limits.py`
- [X] T048 [P] [US1] Implement daily, total, static, and trailing drawdown calculations in `modules/risk/drawdown.py`
- [X] T049 [P] [US1] Implement remaining worst-case loss-to-stop aggregation and unrealized-profit policy in `modules/risk/reserved_risk.py`
- [X] T050 [P] [US1] Implement portfolio, market-category, currency, and correlated-exposure aggregation in `modules/risk/exposure.py`
- [X] T051 [P] [US1] Implement currency conversion, instrument value, price-side, and precision services in `modules/risk/financial_math.py`
- [X] T052 [US1] Implement compliant position sizing and maximum-size search across every effective hard limit in `modules/risk/position_sizing.py`
- [X] T053 [US1] Implement dynamic additional-trade capacity from equity, loss capacity, reservations, exposure, and static ceilings in `modules/risk/trade_capacity.py`
- [X] T054 [US1] Implement serializable candidate risk reservations, expiry, confirmation, and release in `modules/risk/reservations.py`
- [X] T055 [US1] Implement the deterministic Risk Engine authority order and PASS, REDUCE_SIZE, HARD_BLOCK result envelope in `modules/risk/engine.py`
- [X] T056 [P] [US1] Implement deterministic strategy setup input and eligibility ports for seeded validated strategies in `modules/trading/setup_detector.py`
- [X] T057 [US1] Implement deterministic direction, entry, stop, targets, invalidation, risk-reward, and maximum-loss construction in `modules/trading/construction.py`
- [X] T058 [P] [US1] Implement the critic invocation contract and conservative unavailable/invalid-output result in `modules/trading/critic.py`
- [X] T059 [US1] Implement proposal orchestration that orders facts, strategy, policy, risk, critic, reservation, and HIL-2 persistence in `modules/trading/proposals.py`
- [X] T060 [US1] Implement TAKE, WAIT, and REJECT HIL-2 decisions with TAKE transitioning only to awaiting manual entry in `modules/trading/hil2.py`
- [X] T061 [US1] Implement risk evaluation and current snapshot endpoints in `apps/api/app/routes/risk.py`
- [X] T062 [US1] Implement proposal detail and HIL-2 decision endpoints in `apps/api/app/routes/trade_proposals.py`
- [X] T063 [P] [US1] Implement equity, drawdown, reserved-risk, exposure, and additional-capacity cards in `apps/web/src/features/risk/RiskSnapshot.tsx`
- [X] T064 [P] [US1] Implement HIL-2 evidence, constraints, critic result, and TAKE/WAIT/REJECT controls in `apps/web/src/features/trading/TradeProposalPanel.tsx`
- [X] T065 [US1] Integrate proposal and risk APIs into the trade desk page in `apps/web/src/app/(operations)/trading/page.tsx`
- [X] T066 [US1] Emit risk, proposal, hard-block, and HIL-2 audit/outbox events in `modules/trading/events.py`
- [X] T067 [US1] Add seeded account, policy, position, market, and validated-strategy fixtures for independent US1 validation in `tests/fixtures/pretrade.py`

**Checkpoint**: US1 is independently deployable as safe decision support with test fixtures; no broker write capability exists.

---

## Phase 4: User Story 2 - Select Markets for the Session (Priority: P1)

**Goal**: Produce ranked Forex, metal, and cryptocurrency research with freshness evidence and persist the user's HIL-1 selection or replacement.

**Independent Test**: Run research against replay fixtures, receive at most one ranked candidate per category, replace one instrument, approve the active universe, and verify stale critical sources yield DEGRADED or NO TRADE.

### Tests for User Story 2

- [X] T068 [P] [US2] Add market, macro, calendar, and news adapter conformance tests in `tests/contract/test_research_adapters.py`
- [X] T069 [P] [US2] Add Coinbase sequence, reconnect, gap, and stale-stream tests in `tests/integration/test_coinbase_stream.py`
- [X] T070 [P] [US2] Add normalization and no-future-data property tests in `tests/property/test_market_observations.py`
- [X] T071 [P] [US2] Add deterministic research-ranking and category-cardinality replay tests in `tests/replay/test_daily_research.py`
- [X] T072 [P] [US2] Add HIL-1 research, replacement, approval, and no-trade API contract tests in `tests/contract/test_hil1_contract.py`
- [X] T073 [P] [US2] Add browser tests for ranked evidence, replacement, approval, and degraded states in `tests/e2e/test_market_selection.py`

### Implementation for User Story 2

- [X] T074 [P] [US2] Implement canonical instrument, alias, venue instrument, and normalized observation entities in `modules/market_data/models.py`
- [X] T075 [P] [US2] Implement economic event, market fingerprint, research run, and market selection entities in `modules/analysis/models.py`
- [X] T076 [US2] Create instrument, observation hypertable, event, fingerprint, research, and selection tables in `infra/migrations/versions/0003_market_research.py`
- [X] T077 [P] [US2] Implement the provider-neutral market-data contract in `modules/market_data/ports.py`
- [X] T078 [P] [US2] Implement Twelve Data Forex and metals REST adapter in `adapters/market_data/twelve_data/client.py`
- [X] T079 [P] [US2] Implement Coinbase products, ticker, trades, candles, bid/ask, L2, and history adapter in `adapters/market_data/coinbase/client.py`
- [X] T080 [US2] Implement Coinbase subscriptions, sequencing, reconnect, resync, and stale detection in `adapters/market_data/coinbase/stream.py`
- [X] T081 [P] [US2] Implement CoinGecko discovery and asset-metadata adapter without exchange-price authority in `adapters/market_data/coingecko/client.py`
- [X] T082 [P] [US2] Implement FRED macro and CFTC COT positioning adapters in `adapters/macro/providers.py`
- [X] T083 [P] [US2] Implement configurable economic-calendar normalization and source-health adapter in `adapters/calendar/provider.py`
- [X] T084 [P] [US2] Implement configurable news-provider normalization and health adapter in `adapters/news/provider.py`
- [X] T085 [US2] Implement observation normalization, provenance, freshness, and TimescaleDB persistence in `modules/market_data/ingestion.py`
- [X] T086 [P] [US2] Implement deterministic indicators, swing, structure, liquidity, and volatility features in `modules/analysis/technical.py`
- [X] T087 [P] [US2] Implement macro, event, sentiment, positioning, correlation, and intermarket features in `modules/analysis/context.py`
- [X] T088 [US2] Implement structured regime classification and conflict/instability states in `modules/analysis/regime.py`
- [X] T089 [P] [US2] Implement bounded Forex, metals, and crypto research-role services over structured evidence in `modules/analysis/research_roles.py`
- [X] T090 [US2] Implement daily ranking, data-quality gating, one-per-category selection, and NO TRADE outcomes in `modules/analysis/daily_research.py`
- [X] T091 [US2] Implement research-run, status, and HIL-1 decision endpoints in `apps/api/app/routes/research.py`
- [X] T092 [US2] Implement market cards, evidence, replace action, approval action, and degraded states in `apps/web/src/features/research/MarketSelection.tsx`
- [X] T093 [US2] Schedule daily research, provider refreshes, and cancellation-safe progress updates in `apps/worker/app/tasks/research.py`

**Checkpoint**: US2 can select a bounded session universe without granting trade authority.

---

## Phase 5: User Story 3 - Execute and Manage a Trade Manually (Priority: P1)

**Goal**: Reconcile a manually entered broker position, make actual broker values authoritative, and route management recommendations through HIL-3 without broker writes.

**Independent Test**: TAKE a fixture proposal, publish a matching MT5 position event, reconcile actual values, produce HOLD and one actionable recommendation, and verify Matrades never changes the broker position.

### Tests for User Story 3

- [X] T094 [P] [US3] Add BrokerAdapter and MT5 bridge protocol conformance tests, including absence of write methods, in `tests/contract/test_broker_read_only.py`
- [X] T095 [P] [US3] Add signed-message, replay, heartbeat, stale-state, and reconnect tests in `tests/security/test_mt5_bridge_security.py`
- [X] T096 [P] [US3] Add exact, ambiguous, and no-match reconciliation integration tests in `tests/integration/test_position_reconciliation.py`
- [X] T097 [P] [US3] Add HIL-3 state transition and policy revalidation contract tests in `tests/contract/test_hil3_contract.py`
- [X] T098 [P] [US3] Add broker-change and monitoring replay tests in `tests/replay/test_trade_monitoring.py`
- [X] T099 [P] [US3] Add browser tests for awaiting entry, ambiguous match, active trade, and management approval in `tests/e2e/test_manual_trade_management.py`

### Implementation for User Story 3

- [X] T100 [P] [US3] Define authenticated broker snapshot, position, event, heartbeat, symbol, and history schemas in `packages/broker_sdk/schemas.py`
- [X] T101 [P] [US3] Implement the read-only BrokerAdapter port in `modules/trading/broker_port.py`
- [X] T102 [US3] Implement the authenticated MT5 bridge HTTP/event protocol with no order mutation endpoints in `bridges/mt5/app.py`
- [X] T103 [US3] Implement MT5/Wine account, equity, position, order, history, P&L, and symbol readers in `bridges/mt5/reader.py`
- [X] T104 [P] [US3] Implement bridge heartbeat, clock-skew, version, and capability reporting in `bridges/mt5/health.py`
- [X] T105 [US3] Implement the Matrades MT5 adapter, event ingestion, reconnect, and stale-state handling in `adapters/broker/mt5_bridge/client.py`
- [X] T106 [P] [US3] Implement broker position, broker event, reconciliation, trade, recommendation, and journal-event entities in `modules/trading/broker_models.py`
- [X] T107 [US3] Add broker, reconciliation, trade, and recommendation tables in `infra/migrations/versions/0004_broker_trading.py`
- [X] T108 [US3] Implement awaiting-manual-entry state and reservation expiry/revalidation behavior in `modules/trading/manual_entry.py`
- [X] T109 [US3] Implement deterministic position matching by instrument, direction, time, price, size, and approved setup in `modules/trading/reconciliation.py`
- [X] T110 [US3] Implement explicit user resolution for ambiguous position matches in `modules/trading/reconciliation_decisions.py`
- [X] T111 [US3] Promote reconciled actual entry, size, protections, fees, and P&L to monitoring authority in `modules/trading/active_trades.py`
- [X] T112 [P] [US3] Implement actual-position monitoring inputs and deterministic invalidation, event, risk, and policy checks in `modules/trading/monitor.py`
- [X] T113 [US3] Implement bounded trade-monitor interpretation with HOLD, MOVE_SL, PARTIAL_TP, EARLY_EXIT, and FULL_EXIT outputs in `modules/trading/monitor_agent.py`
- [X] T114 [US3] Revalidate actionable management recommendations and persist APPROVE, WAIT, and REJECT HIL-3 decisions in `modules/trading/hil3.py`
- [X] T115 [US3] Implement reconciliation and trade recommendation endpoints in `apps/api/app/routes/trade_management.py`
- [X] T116 [P] [US3] Implement MT5 connection and bridge-health UI in `apps/web/src/features/connections/MT5Connection.tsx`
- [X] T117 [US3] Implement awaiting-entry, match resolution, actual-position, and HIL-3 controls in `apps/web/src/features/trading/TradeManagement.tsx`
- [X] T118 [US3] Schedule monitoring, bridge-heartbeat, broker-event, and reconciliation workers in `apps/worker/app/tasks/trading.py`

**Checkpoint**: US3 assists live management using reconciled broker truth while every execution or modification remains manual.

---

## Phase 6: User Story 4 - Create and Validate a Strategy (Priority: P2)

**Goal**: Bring AI-generated, AI-assisted, human-created, and imported strategies through one canonical, deterministic, equally validated lifecycle.

**Independent Test**: Create one manual and one assisted draft, decide suggestions individually, detect a duplicate, compile a complete unique strategy, run chronological validation and paper evidence, and promote only the passing version.

### Tests for User Story 4

- [X] T119 [P] [US4] Add strategy draft, assistance, similarity, submit, and validation API contract tests in `tests/contract/test_strategy_api.py`
- [X] T120 [P] [US4] Add canonicalization, provenance, lifecycle, and equal-origin property tests in `tests/property/test_strategy_invariants.py`
- [X] T121 [P] [US4] Add compiler and generated edge-case unit tests for the declarative rule vocabulary in `tests/unit/strategies/test_compiler.py`
- [X] T122 [P] [US4] Add look-ahead, chronological replay, transaction-cost, and ledger invariants in `tests/replay/test_backtest_integrity.py`
- [X] T123 [P] [US4] Add out-of-sample, walk-forward, stress, Monte Carlo, and prop-rule validation tests in `tests/integration/test_strategy_validation.py`
- [X] T124 [P] [US4] Add browser tests for all four origins, suggestion decisions, similarity, backtest, and promotion in `tests/e2e/test_strategy_lifecycle.py`

### Implementation for User Story 4

- [X] T125 [P] [US4] Define strategy family, pattern, regime, dependency, horizon, signal, and trade taxonomy in `packages/strategy_sdk/taxonomy.py`
- [X] T126 [P] [US4] Define the canonical strategy specification, deterministic rule vocabulary, and runtime interface in `packages/strategy_sdk/schema.py`
- [X] T127 [P] [US4] Implement strategy draft, rule revision, suggestion, change set, strategy, version, fingerprint, and lineage entities in `modules/strategies/models.py`
- [X] T128 [P] [US4] Implement artifact, backtest, validation, paper run, promotion, compatibility, health, and performance entities in `modules/backtesting/models.py`
- [X] T129 [US4] Add strategy repository, provenance, similarity, validation, paper, and promotion tables in `infra/migrations/versions/0005_strategies.py`
- [X] T130 [P] [US4] Seed initial strategy families and reusable structure/liquidity patterns in `modules/strategies/seeds.py`
- [X] T131 [US4] Implement resumable draft creation for natural language, partial, manual, copied, and imported inputs in `modules/strategies/drafts.py`
- [X] T132 [P] [US4] Implement completeness, ambiguity, inconsistency, optional-rule, and deterministic-implementation checks in `modules/strategies/completeness.py`
- [X] T133 [US4] Implement bounded strategy-assistant suggestions, parameter ranges, challenges, and weakness explanations in `modules/strategies/assistant.py`
- [X] T134 [US4] Implement individual ACCEPT, EDIT, REJECT and bulk-preview workflows without implicit canonical mutation in `modules/strategies/suggestions.py`
- [X] T135 [P] [US4] Implement rule-level origin, AI contribution, user decision, revision, and author provenance in `modules/strategies/provenance.py`
- [X] T136 [P] [US4] Implement canonical fingerprints and exact duplicate detection in `modules/strategies/fingerprints.py`
- [X] T137 [P] [US4] Implement structural, semantic-candidate, parameter, and behavioral similarity assessment in `modules/strategies/similarity.py`
- [X] T138 [US4] Implement duplicate, near-duplicate, variant, new-version, and new-strategy classification and actions in `modules/strategies/identity.py`
- [X] T139 [US4] Compile canonical specifications into deterministic evaluators with versioned artifacts in `modules/strategies/compiler.py`
- [X] T140 [P] [US4] Generate deterministic boundary and invalid-input tests from strategy specifications in `modules/strategies/test_generation.py`
- [X] T141 [US4] Implement legal lifecycle transitions from DRAFT through ACTIVE plus DEGRADED, SUSPENDED, and RETIRED in `modules/strategies/lifecycle.py`
- [X] T142 [P] [US4] Implement chronological historical replay with point-in-time data access in `modules/backtesting/replay.py`
- [X] T143 [P] [US4] Implement spread, commission, slippage, swap, funding, contract-term, and missing-cost policy in `modules/backtesting/costs.py`
- [X] T144 [US4] Implement the deterministic trade ledger and metrics including expectancy, R, drawdown, streaks, MAE, and MFE in `modules/backtesting/ledger.py`
- [X] T145 [P] [US4] Implement out-of-sample and walk-forward validation in `modules/backtesting/validation.py`
- [X] T146 [P] [US4] Implement stress and Monte Carlo validation in `modules/backtesting/stress.py`
- [X] T147 [P] [US4] Implement versioned prop-firm and internal-rule simulation in `modules/backtesting/policy_simulation.py`
- [X] T148 [US4] Implement paper accounts, live paper signals, positions, and shared evaluator usage in `modules/backtesting/paper.py`
- [X] T149 [US4] Implement promotion criteria comparing backtest, validation, policy simulation, and paper evidence in `modules/backtesting/promotion.py`
- [X] T150 [US4] Implement origin-neutral compatibility, strategy health, suitability ranking, and NO_SUITABLE_STRATEGY in `modules/strategies/selection.py`
- [X] T151 [US4] Implement strategy draft, assistance, suggestion, similarity, submit, validation, and promotion endpoints in `apps/api/app/routes/strategies.py`
- [X] T152 [P] [US4] Implement structured strategy builder, rule editor, provenance, and assistant panel in `apps/web/src/features/strategies/StrategyBuilder.tsx`
- [X] T153 [P] [US4] Implement similarity comparison and branch/reuse/version actions in `apps/web/src/features/strategies/SimilarityReview.tsx`
- [X] T154 [P] [US4] Implement backtest, validation, paper, and promotion evidence views in `apps/web/src/features/strategies/ValidationResults.tsx`
- [X] T155 [US4] Schedule compile, backtest, validation, similarity, paper, and promotion jobs with immutable input references in `apps/worker/app/tasks/strategies.py`

**Checkpoint**: All strategy origins use one trust pipeline and no generated executable behavior enters live use without deterministic validation and promotion.

---

## Phase 7: User Story 5 - Configure Accounts, Rules, and Security (Priority: P2)

**Goal**: Securely activate users and configure credentials, provider connections, accounts, versioned prop rules, and internal guardrails through the UI.

**Independent Test**: Complete signup through MFA, create and test a masked credential, configure personal and prop accounts with rules and guardrails, and prove sensitive or weaker-limit changes require step-up and audit.

### Tests for User Story 5

- [X] T156 [P] [US5] Add signup, verification, MFA, recovery, session, and step-up API contract tests in `tests/contract/test_identity_api.py`
- [X] T157 [P] [US5] Add credential encryption, masking, non-disclosure, prompt exclusion, and rotation security tests in `tests/security/test_credential_vault.py`
- [X] T158 [P] [US5] Add owner isolation, role denial, session revocation, and sensitive-action authorization tests in `tests/security/test_authorization.py`
- [X] T159 [P] [US5] Add prop-ruleset versioning, activation, import-review, and strictest-limit integration tests in `tests/integration/test_account_configuration.py`
- [X] T160 [P] [US5] Add browser tests for activation, credentials, accounts, prop rules, guardrails, and step-up in `tests/e2e/test_secure_configuration.py`

### Implementation for User Story 5

- [X] T161 [P] [US5] Implement user, email verification, MFA enrollment, recovery code, session, and step-up entities in `modules/identity/models.py`
- [X] T162 [P] [US5] Implement encrypted credential versions, connection, and health observation entities in `modules/credentials/models.py`
- [X] T163 [P] [US5] Implement prop firm, program, versioned ruleset/rule, guardrail profile, and guardrail rule entities in `modules/prop_firms/models.py`
- [X] T164 [US5] Add identity, credential, connection, prop-firm, and guardrail tables in `infra/migrations/versions/0006_secure_configuration.py`
- [X] T165 [US5] Implement registration, password hashing, email verification, TOTP enrollment/challenge, recovery codes, password reset, and session revocation in `modules/identity/service.py`
- [X] T166 [US5] Implement step-up MFA policies for credentials, security, broker settings, hard rules, and guardrail reductions in `modules/identity/step_up.py`
- [X] T167 [US5] Implement envelope encryption, reference-only access, masked responses, replacement, rotation, and deletion in `modules/credentials/vault.py`
- [X] T168 [US5] Implement generic provider connection registration, credential references, test workflow, and health history in `modules/connections/service.py`
- [X] T169 [US5] Implement account CRUD, personal/prop classification, currency, platform, mode, status, and connection binding in `modules/accounts/service.py`
- [X] T170 [US5] Implement prop-firm hierarchy, structured rule types, versioning, verification, activation, and historical retention in `modules/prop_firms/service.py`
- [X] T171 [US5] Implement non-authoritative rule extraction/import preview with explicit user verification in `modules/prop_firms/import_assistant.py`
- [X] T172 [US5] Implement global, account, strategy, exposure, loss, session, event, freshness, and trade-count guardrail configuration in `modules/policy/guardrails.py`
- [X] T173 [US5] Implement identity, credential, connection, account, prop-ruleset, and guardrail endpoints in `apps/api/app/routes/configuration.py`
- [X] T174 [P] [US5] Implement signup, MFA, recovery, session, and step-up screens in `apps/web/src/features/security/SecuritySettings.tsx`
- [X] T175 [P] [US5] Implement masked credential and provider connection management screens in `apps/web/src/features/configuration/Connections.tsx`
- [X] T176 [US5] Implement account, prop-firm rules, import review, effective limits, and guardrail screens in `apps/web/src/features/configuration/AccountRules.tsx`

**Checkpoint**: Configuration is UI-first, owner-scoped, versioned, step-up protected, auditable, and never returns a stored secret.

---

## Phase 8: User Story 6 - Configure Agents Without Changing Their Authority (Priority: P2)

**Goal**: Run every fixed logical agent through Codex App Server by default while allowing an explicit per-agent or per-profile LiteLLM alternative without automatic cross-runtime fallback or increased authority.

**Independent Test**: Verify all 15 agents resolve to Codex by default, explicitly assign one LiteLLM profile, exercise a compatible same-runtime fallback, exhaust Codex fallbacks, and prove selected/actual runtime audit, no cross-runtime retry, independent prompt resolution, and unchanged tool rights.

### Tests for User Story 6

- [X] T177 [P] [US6] Add fixed-registry, required-role protection, and default `CODEX_APP_SERVER` resolution contract tests in `tests/contract/test_agent_registry.py`
- [X] T178 [P] [US6] Add independent system/user prompt resolution matrix property tests in `tests/property/test_prompt_resolution.py`
- [X] T179 [P] [US6] Add Codex App Server supervision, explicit LiteLLM opt-in, same-runtime fallback, no cross-runtime retry, timeout, schema-validation, and safe-failure tests in `tests/integration/test_agent_runtime.py`
- [X] T180 [P] [US6] Add runtime-selection authorization, tool least-privilege, and no broker/hard-policy/guardrail write authority tests in `tests/security/test_agent_permissions.py`
- [X] T181 [P] [US6] Add browser tests for Codex defaults, optional LiteLLM sync and assignment, runtime-bound profiles, prompt inheritance, and test execution in `tests/e2e/test_agent_configuration.py`

### Implementation for User Story 6

- [X] T182 [P] [US6] Implement runtime-typed models and profiles, Codex-default agent definitions, versioned runtime selection, prompts, permission sets, and selected/actual runtime execution entities in `modules/agents/models.py`
- [X] T183 [US6] Add runtime type and selection constraints, same-runtime fallback enforcement, agent configuration, prompt, permission, and execution-audit tables in `infra/migrations/versions/0007_agents.py`
- [X] T184 [P] [US6] Implement the default Python SDK/stdio Codex App Server adapter in `adapters/agent_runtime/codex_app_server/client.py` and the optional explicitly selected LiteLLM adapter in `adapters/agent_runtime/litellm/client.py`
- [X] T185 [US6] Seed and protect the 15 required logical identities with `CODEX_APP_SERVER` defaults in `modules/agents/registry.py`
- [X] T186 [US6] Implement runtime-bound model profiles, explicit LiteLLM assignment, capability requirements, same-runtime fallback compatibility, and activation validation in `modules/agents/model_profiles.py`
- [X] T187 [US6] Implement independent system and user prompt versioning and exact override-to-orchestrator-to-platform resolution in `modules/agents/prompts.py`
- [X] T188 [US6] Implement independently versioned tool permissions and prove runtime, model, or prompt changes cannot alter authority in `modules/agents/permissions.py`
- [X] T189 [US6] Implement runtime-first routing, versioned invocation/results, bounded execution, Codex process supervision, same-runtime retries/fallbacks, and cross-runtime safe failure in `modules/agents/runtime.py`
- [X] T190 [US6] Persist selected/actual runtime, selection source, resolved prompts, provider/model/fallback, tools, evidence, timings, status, and errors in `modules/agents/execution_audit.py`
- [X] T191 [US6] Implement runtime catalog, model/profile, agent configuration, prompt, permission, health, and test-run endpoints in `apps/api/app/routes/agents.py`
- [X] T192 [P] [US6] Implement Codex runtime health and defaults plus optional LiteLLM connection, model sync, and runtime-bound profile screens in `apps/web/src/features/agents/ModelProfiles.tsx`
- [X] T193 [P] [US6] Implement explicit per-agent runtime selection and provider/model/fallback/parameter/credential/tool configuration in `apps/web/src/features/agents/AgentConfiguration.tsx`
- [X] T194 [US6] Implement independent system/user prompt inheritance previews, versions, capability errors, and test execution in `apps/web/src/features/agents/PromptConfiguration.tsx`

**Checkpoint**: All required agents default to Codex App Server; LiteLLM runs only after explicit assignment, fallbacks stay within one runtime, and runtime/model/prompt changes never alter authority.

---

## Phase 9: User Story 7 - Retrieve Context Without Replacing Facts (Priority: P3)

**Goal**: Ingest and retrieve authorized contextual knowledge with provenance while preventing semantic results from supplying authoritative market, account, policy, risk, or performance facts.

**Independent Test**: Ingest sources for two owners, retrieve cited context for one owner, prove cross-owner isolation and authority routing, then disable retrieval and verify deterministic safety services continue while dependent research becomes DEGRADED.

### Tests for User Story 7

- [X] T195 [P] [US7] Add knowledge source, ingestion, search, reprocess, disable, and delete API contract tests in `tests/contract/test_knowledge_api.py`
- [X] T196 [P] [US7] Add owner/account isolation, malicious-document, and provenance security tests in `tests/security/test_knowledge_isolation.py`
- [X] T197 [P] [US7] Add authority-router tests forbidding semantic-only policy, risk, current-fact, performance, and duplicate decisions in `tests/contract/test_knowledge_authority.py`
- [X] T198 [P] [US7] Add unavailable-vector-index degradation and deterministic-service continuity tests in `tests/failure/test_knowledge_degradation.py`

### Implementation for User Story 7

- [X] T199 [P] [US7] Implement knowledge source, document, segment, ingestion run, and retrieval audit entities in `modules/knowledge/models.py`
- [X] T200 [US7] Add owner-scoped knowledge, vector, provenance, and ingestion tables and indexes in `infra/migrations/versions/0008_knowledge.py`
- [X] T201 [P] [US7] Implement replaceable embedding provider and semantic index contracts in `modules/knowledge/ports.py`
- [X] T202 [US7] Implement authorized upload, extraction, chunking, embedding, idempotent reprocessing, disable, and deletion jobs in `modules/knowledge/ingestion.py`
- [X] T203 [US7] Implement hybrid search, provenance, version/date/tag filters, authorization, and retrieval audit in `modules/knowledge/search.py`
- [X] T204 [US7] Implement the record-type authority router and non-authoritative KnowledgeTool envelope in `modules/knowledge/authority.py`
- [X] T205 [US7] Implement knowledge source, ingestion status, health, and search endpoints in `apps/api/app/routes/knowledge.py`
- [X] T206 [US7] Implement source management, reprocess/delete controls, retrieval provenance, and degraded health UI in `apps/web/src/features/knowledge/KnowledgeSources.tsx`

**Checkpoint**: Context is owner-scoped, cited, auditable, and optional to deterministic safety and essential monitoring.

---

## Phase 10: User Story 8 - Review Decisions and Performance (Priority: P3)

**Goal**: Reconstruct decisions and broker outcomes, calculate attributable performance from structured records, expose operational health, and create controlled research actions without mutating active strategies.

**Independent Test**: Open a completed trade and reconstruct its full evidence chain, compare performance by strategy/regime/account, trigger a research draft from degradation, and verify the active strategy is unchanged.

### Tests for User Story 8

- [X] T207 [P] [US8] Add journal reconstruction and append-only event contract tests in `tests/contract/test_journal_reconstruction.py`
- [X] T208 [P] [US8] Add deterministic performance aggregation and attribution property tests in `tests/property/test_performance_metrics.py`
- [X] T209 [P] [US8] Add controlled degradation-trigger and active-version immutability integration tests in `tests/integration/test_strategy_health_actions.py`
- [X] T210 [P] [US8] Add notification adapter, deduplication, preference, and delivery-state contract tests in `tests/contract/test_notifications.py`
- [X] T211 [P] [US8] Add browser tests for approval inbox, journal, performance, health, audit, and notifications in `tests/e2e/test_review_and_performance.py`

### Implementation for User Story 8

- [X] T212 [P] [US8] Implement journal projection, evidence links, narrative index, and immutable decision reconstruction in `modules/journal/service.py`
- [X] T213 [P] [US8] Implement performance record, strategy health, research trigger, and notification entities in `modules/performance/models.py`
- [X] T214 [US8] Add journal projection, performance, health, trigger, and notification tables in `infra/migrations/versions/0009_review_operations.py`
- [X] T215 [US8] Implement structured metrics and attribution by strategy/version, instrument, category, regime, session, account, prop firm, and agent configuration in `modules/performance/metrics.py`
- [X] T216 [US8] Implement strategy health thresholds and actions that create drafts, research requests, or suspension reviews without mutation in `modules/performance/strategy_health.py`
- [X] T217 [P] [US8] Implement normalized in-product notification creation, preferences, urgency, deduplication, and delivery state in `modules/notifications/service.py`
- [X] T218 [P] [US8] Implement replaceable email, Telegram, and browser-push notification adapters in `adapters/notifications/channels.py`
- [X] T219 [US8] Implement journal, performance, health, audit, notification, and centralized approval-inbox endpoints in `apps/api/app/routes/operations.py`
- [X] T220 [P] [US8] Implement reconstructable journal timeline and evidence detail UI in `apps/web/src/features/journal/JournalTimeline.tsx`
- [X] T221 [P] [US8] Implement performance filters, attribution, comparisons, and strategy health UI in `apps/web/src/features/performance/PerformanceDashboard.tsx`
- [X] T222 [P] [US8] Implement HIL-1/HIL-2/HIL-3 grouped approval inbox with urgency and state labels in `apps/web/src/features/approvals/ApprovalInbox.tsx`
- [X] T223 [P] [US8] Implement source, agent, model, broker, bridge, knowledge, and notification health dashboard in `apps/web/src/features/health/HealthDashboard.tsx`
- [X] T224 [US8] Schedule journal projection, performance rollups, strategy-health evaluation, and notification delivery in `apps/worker/app/tasks/operations.py`

**Checkpoint**: Every material decision is reconstructable and learning produces controlled proposals, never silent live mutation.

---

## Phase 11: Polish & Cross-Cutting Release Gates

**Purpose**: Validate the integrated platform against constitutional invariants and measurable success criteria, then produce operable release evidence.

- [X] T225 [P] Add structured logging, correlation IDs, traces, metrics, and secret-safe exporters in `infra/observability/otel-collector.yaml`
- [X] T226 [P] Add API, background worker, Codex agent worker, optional LiteLLM, web, PostgreSQL, Redis, provider, and bridge operational dashboards and alerts in `infra/observability/dashboards/matrades.json`
- [X] T227 Add failure-injection coverage for stale market/account data, Codex process and runtime outage, exhausted same-runtime fallbacks, prohibited LiteLLM auto-fallback, provider outage, Redis loss, database failover, and worker restart in `tests/failure/test_safe_failure_matrix.py`
- [X] T228 Add security tests for broken access control, CSRF, rate limits, unsafe uploads, injection, SSRF, session fixation, and audit tampering in `tests/security/test_platform_threats.py`
- [X] T229 Add a repository-wide static and runtime assertion that no V1 broker-write interface or endpoint exists in `tests/security/test_no_broker_writes.py`
- [X] T230 Add migration upgrade, downgrade, rollback, compatibility, TimescaleDB, and pgvector release tests in `tests/integration/test_migration_release.py`
- [X] T231 Add backup, point-in-time restore, blob recovery, and disaster-recovery verification in `infra/deployment/restore-runbook.md`
- [X] T232 Add retention, export, account deletion, credential destruction, and audit-evidence policies in `docs/data-lifecycle.md`
- [X] T233 Add performance tests for five-second pre-trade decisions, ten-minute research, two-second UI propagation, and concurrent reservations in `tests/integration/test_performance_slos.py`
- [ ] T234 Add the full signup-to-HIL-1 journey with real API, worker, database, and browser components in `tests/e2e/test_release_signup_to_hil1.py`
- [ ] T235 Add the full HIL-2-to-manual-MT5-reconciliation journey in `tests/e2e/test_release_hil2_to_reconciliation.py`
- [ ] T236 Add the full monitoring-to-HIL-3-to-journal/performance journey in `tests/e2e/test_release_hil3_closed_loop.py`
- [ ] T237 Add full AI-assisted, AI-generated, human-created, and imported strategy lifecycle journeys in `tests/e2e/test_release_strategy_origins.py`
- [ ] T238 Add full risk hard-block, reduce-size, prop-firm difference, correlation, and dynamic-capacity journeys in `tests/e2e/test_release_risk_controls.py`
- [ ] T239 Add full Codex-default, explicit LiteLLM opt-in, same-runtime fallback, no cross-runtime retry, per-agent model/prompt, and permission-isolation journeys in `tests/e2e/test_release_agent_configuration.py`
- [X] T240 Map SC-001 through SC-015 to executable evidence and CI artifact locations in `tests/acceptance/success_criteria.md`
- [ ] T241 Execute every scenario and stop condition from the validation guide and record evidence in `specs/001-matrades-product-platform/validation-report.md`
- [X] T242 [P] Document local setup, configuration, migrations, provider simulators, MT5 bridge, tests, and troubleshooting in `README.md`
- [X] T243 [P] Document API, event, Codex App Server and optional LiteLLM adapters, runtime routing, authority, state-machine, and operational conventions in `docs/architecture.md`
- [ ] T244 Run dependency, license, container, secret, and supply-chain checks and record approved exceptions in `docs/release/security-review.md`

**Checkpoint**: All required quality gates and SC-001 through SC-015 have reproducible release evidence.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 - Setup**: Starts immediately.
- **Phase 2 - Foundational**: Depends on Phase 1 and blocks all user stories.
- **US1**: Starts after Foundation and uses seeded authoritative fixtures, making it the smallest safe MVP.
- **US2**: Starts after Foundation; its real market/research outputs can later replace US1 fixtures.
- **US3**: Starts after Foundation and the US1 proposal/HIL-2 contracts; it can use proposal fixtures until US1 integration.
- **US4**: Starts after Foundation; its promoted strategies can later replace US1 strategy fixtures and feed US2 opportunity scoring.
- **US5**: Starts after Foundation; it productionizes account, policy, and owner configuration consumed by US1 while US1 remains independently testable with fixtures.
- **US6**: Starts after Foundation; US1-US4 use conservative role ports or deterministic behavior until the configurable runtime is integrated.
- **US7**: Starts after Foundation and is explicitly non-blocking for deterministic safety and essential monitoring.
- **US8**: Starts after Foundation using event fixtures, but complete reconstruction and attribution integrate outputs from US1-US7.
- **Polish**: Starts when the set of stories targeted for release is complete; full release gates require all eight.

### User Story Dependency Graph

```text
Setup -> Foundation -> US1 ---------------------> US3 -----------+
                    |  \                           \              |
                    |   +-> US2 -------------------+--------------+-> US8 -> Release Gates
                    |   +-> US4 -------------------+--------------+
                    |   +-> US5 -------------------+--------------+
                    |   +-> US6 -------------------+--------------+
                    |   +-> US7 (context only) ----+--------------+
                    +-> US8 (fixture-driven start) ----------------+
```

### Within Each User Story

1. Write the story's tests and confirm they fail for the intended missing behavior.
2. Create entities and migrations before services that persist them.
3. Implement deterministic rules and state transitions before AI interpretation.
4. Implement services before endpoints and UI integration.
5. Complete the independent test before integrating later stories.

---

## Parallel Execution Examples

### User Story 1

After T045 establishes its schema, T046-T051 can proceed in parallel; T052-T055 then converge into T059. UI work T063-T064 can proceed against the generated contract while backend orchestration is implemented.

### User Story 2

T078-T084 are independent adapters and can run in parallel. T086-T087 can run alongside ingestion once normalized fixture schemas exist. Contract, property, replay, and browser tests T068-T073 use separate files.

### User Story 3

Bridge schemas/health T100 and T104, broker models T106, monitoring rules T112, and MT5 UI T116 can proceed in parallel after their interfaces are fixed.

### User Story 4

Canonical schema T126 unlocks parallel work on completeness T132, provenance T135, fingerprints T136, replay T142, costs T143, validation T145, stress T146, and policy simulation T147.

### User Story 5

Identity, credential, and prop-firm entities T161-T163 can be implemented in parallel, as can the security, connection, and account/rule UI slices T174-T176 after the API schemas stabilize.

### User Story 6

Codex/LiteLLM adapters T184, fixed Codex-default registry T185, runtime-bound profiles T186, prompts T187, and permissions T188 can proceed in parallel against the agent contracts before converging in runtime router T189.

### User Story 7

The embedding/index port T201 and security/authority/failure tests T196-T198 can proceed in parallel; UI T206 can be built against contract fixtures while ingestion and search are implemented.

### User Story 8

Journal projection T212, performance models T213, notification service T217, channel adapters T218, and the four UI views T220-T223 are separable after shared event contracts exist.

---

## Implementation Strategy

### MVP First: Safe Trade Decision

1. Complete Setup and Foundation.
2. Complete US1 using seeded account, policy, market, and validated-strategy fixtures.
3. Verify PASS, REDUCE_SIZE, HARD_BLOCK, complete equity evidence, HIL-2 decisions, reservation concurrency, and absence of broker writes.
4. Stop and review the MVP before adding live providers or broker monitoring.

### Incremental Delivery

1. Add US2 for real daily research and HIL-1.
2. Add US3 for manual-entry reconciliation and HIL-3.
3. Add US4 for strategy creation and equal validation.
4. Add US5 and US6 to productionize secure user configuration and agent runtime.
5. Add US7 for bounded context and US8 for the closed evidence/performance loop.
6. Complete the integrated release gates.

### Milestone Mapping from the Attached Draft

- **Secure Platform**: Setup, Foundation, and US5
- **Configurable Multi-Agent Runtime**: US6
- **Safe Account Core and Trading Recommendation**: US1
- **Research Data Platform and Daily Selection**: US2
- **Strategy Platform and Validation**: US4
- **Broker Monitoring**: US3
- **Closed Learning Loop**: US7, US8, and Release Gates

---

## Notes

- Deterministic services own financial math, policy, risk, lifecycle transitions, and setup evaluation; agents may interpret but never replace these decisions.
- PostgreSQL owns durable workflow, approvals, versions, jobs, and audit evidence; Redis and LangGraph checkpoints remain non-authoritative.
- Every required agent defaults to the Codex App Server runtime; LiteLLM requires explicit versioned assignment, and fallbacks never cross runtimes automatically.
- Any missing or inconsistent critical current fact yields WAIT, BLOCK, DEGRADED, or NO TRADE, never fabricated certainty.
- Strategy origin never changes the validation standard.
- Every implementation task is complete only when its preceding tests pass and its material state changes emit reconstructable audit evidence.

---

## Phase 12: Convergence

**Purpose**: Close implementation gaps found by comparing the present codebase with the governing specification, implementation plan, and constitution. These tasks complement, and do not replace, the open release-gate tasks T234–T239, T241, and T244.

- [ ] T245 [CRITICAL] Replace process-local authoritative state with PostgreSQL-backed repositories and transactional units of work for accounts, configuration, agents, research, proposals, approvals, reservations, monitoring, knowledge, notifications, audit, and idempotency; publish committed domain events through a durable outbox and remove module-global dictionaries/lists from `apps/api/app/routes/`, `modules/observability/audit.py`, and affected services (Constitution X; plan authority/state decisions; gap: missing)
- [X] T246 [CRITICAL] Complete verified-email signup, password login, TOTP challenge validation, one-time recovery-code consumption, password recovery, durable session creation/revocation, step-up authentication, role checks, and owner scoping; derive actor and owner identity from authenticated sessions on every protected API instead of request-supplied identifiers in `modules/identity/`, `apps/api/app/dependencies/`, and `apps/api/app/routes/` (FR-008–FR-014; Constitution VIII; gap: partial)
- [X] T247 [CRITICAL] Make pre-trade risk evaluation authoritative and fail closed by capturing a fresh, source-versioned equity snapshot with every FR-023/FR-032 field, resolving prop-firm and internal constraints in strict authority order, reserving worst-case open risk, evaluating correlated/category exposure and dynamic trade capacity, and committing concurrent reservations serializably with complete limiting-source evidence in `modules/risk/`, `modules/trading/proposals.py`, and persistence migrations (FR-022–FR-033; Constitution I, III, VI; gap: contradicts)
- [ ] T248 [CRITICAL] Implement durable HIL-1, HIL-2, and HIL-3 state machines with server-created proposals, permissioned approve/reject/replace/rerun/no-trade decisions, expiry and stale-data transitions, immutable evidence snapshots, idempotent commands, audit/outbox emission, manual-entry reconciliation, and policy-derived management recommendations; never accept policy validity or transition authority from the client in `modules/trading/`, `modules/research/`, `apps/api/app/routes/trade_proposals.py`, and `apps/api/app/routes/trade_management.py` (FR-001–FR-007, FR-081–FR-090; Constitution II; gap: partial)
- [ ] T249 [CRITICAL] Align and secure the MT5 bridge protocol by enforcing HMAC verification, timestamp skew, nonce replay protection, message sequence ordering, capability and heartbeat negotiation on every route; expose the snapshot/history/position event contract consumed by the API, and add reconnect, duplicate, out-of-order, stale-feed, and position-matching handling in `bridges/mt5/` and `modules/brokers/` (FR-085–FR-090; Constitution IX; gap: contradicts)
- [ ] T250 [CRITICAL] Implement the Codex-first agent runtime as an actual Codex App Server SDK/stdio supervisor with lifecycle, health, cancellation, structured-output validation, bounded tool permissions, persisted provider/model/profile/prompt versions, execution audit, and a real runtime test endpoint; keep LiteLLM Gateway opt-in per agent and prohibit implicit cross-runtime fallback in `modules/agents/`, `apps/api/app/routes/agents.py`, and `apps/worker/` (FR-044–FR-054, FR-101–FR-102; Constitution VII; gap: missing)
- [ ] T251 [CRITICAL] Persist an append-only reconstruction chain linking market and knowledge evidence, source timestamps, strategy/code/config/prompt/model versions, risk snapshots, critic outputs, human decisions, notifications, and broker events; implement owner-scoped audit, journal, proposal, and incident reconstruction endpoints in `modules/observability/`, `modules/trading/`, `modules/performance/`, and `apps/api/app/routes/operations.py` (FR-091, FR-099–FR-100; Constitution X; gap: partial)
- [ ] T252 [HIGH] Complete account, policy, prop-firm rule, internal guardrail, instrument/category, reset-basis, currency, effective-limit contributor, import-review, and immutable version-history models and APIs, including historical effective-configuration lookup and frontend management views in `modules/accounts/`, `modules/risk/policies.py`, `apps/api/app/routes/configuration.py`, and `apps/web/src/features/configuration/` (FR-015–FR-021; gap: partial)
- [ ] T253 [HIGH] Replace the in-memory single-key credential store with persistent envelope encryption backed by a configured KMS/key-encryption abstraction, opaque secret references, authenticated rotation/replace/test/delete operations, key-version migration, redacted responses/logging, step-up authorization, and audit events in `modules/credentials/` and configuration APIs (FR-010–FR-013; Constitution VIII; gap: partial)
- [ ] T254 [HIGH] Complete Twelve Data and Coinbase REST/WebSocket adapters plus pluggable calendar/news ingestion, normalized quote/candle/trade/order-book/event schemas, source and observation timestamps, provenance, health and stale-data state, reconnect/backfill/deduplication, and TimescaleDB persistence in `modules/market_data/`, `apps/worker/`, and database migrations (FR-034–FR-040; gap: partial)
- [ ] T255 [HIGH] Replace caller-supplied research rankings with a scheduled, persisted daily research workflow that gathers category data, computes technical/fundamental/sentiment/regime features, invokes bounded analyst and critic agents, stores structured fingerprints and evidence, ranks exactly one candidate per configured category, and supports permissioned replace/rerun/no-trade and degraded states in `modules/research/`, `apps/worker/`, and `apps/api/app/routes/research.py` (FR-002, FR-041–FR-043; gap: partial)
- [ ] T256 [HIGH] Expand the canonical strategy contract to cover regimes, dependencies, confirmations, filters, invalidation, stops, targets, management, sessions, events, reproducibility metadata, and immutable provenance; align lifecycle states and guarded transitions exactly with the specification and add typed similarity plus versioned branch/review actions for manual, agent-authored, and imported strategies in `packages/strategy_sdk/` and `modules/strategies/` (FR-055–FR-068, FR-073–FR-074; Constitution IV; gap: contradicts)
- [ ] T257 [HIGH] Implement point-in-time-safe backtests with realistic costs and complete metrics/attribution, out-of-sample and walk-forward validation, stress and Monte Carlo analysis, deterministic policy checks, paper-trading evidence, and approval/promotion gates through one origin-neutral evaluator shared by UI, API, and workers in `modules/backtesting/`, `modules/strategies/validation.py`, and `apps/worker/` (FR-069–FR-072; gap: partial)
- [ ] T258 [HIGH] Implement the authorized knowledge-source lifecycle with durable metadata and blobs, extraction/chunking/embedding/indexing, idempotent reprocessing, disable/delete/status operations, vector and lexical hybrid retrieval with owner/category/date/tag filters, precise source/chunk/version citations, retrieval audit, and fail-safe degraded behavior in `modules/knowledge/` and `apps/api/app/routes/knowledge.py` (FR-075–FR-080; gap: partial)
- [X] T259 [HIGH] Replace hard-coded web fixtures with authenticated typed API clients, session and step-up flows, query/mutation state, SSE or equivalent realtime updates, error/degraded/empty/loading states, and accessible operational controls for configuration, agents, research, strategy, HIL approvals, monitoring, knowledge, notifications, audit, journal, and performance in `apps/web/src/` (FR-011, FR-046, FR-079, FR-094–FR-098; Constitution VIII; gap: partial)
- [ ] T260 [HIGH] Implement durable idempotent worker jobs with persisted progress, cancellation, retry/backoff, dead-letter handling, and outbox consumption; replace static health and recording-only notifications with measured dependency health, structured logs/traces/metrics, alert thresholds, user preferences, persistent in-product delivery, and configured email/Telegram/push adapters in `apps/worker/`, `modules/observability/`, `modules/notifications/`, and `apps/api/app/routes/operations.py` (FR-097–FR-100; plan Stage 10; gap: partial)
- [ ] T261 [HIGH] Replace source-text and direct-function release checks for completed foundation tasks with executable PostgreSQL/Timescale/vector migrations, real API authentication/authorization tests, transactional outbox/idempotency and failure-recovery tests, provider/MT5 contract tests, and browser-level assertions using disposable integration infrastructure in `tests/contract/`, `tests/integration/`, `tests/e2e/`, and `apps/web/` while retaining the open T234–T244 release gates (plan verification strategy; Constitution IX–X; gap: partial)
