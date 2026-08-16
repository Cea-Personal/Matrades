# Tasks: TraderX Core Platform

**Input**: Design documents from `/specs/001-traderx-core-platform/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`, and TraderX Constitution v1.1.0

**Tests**: Tests are mandatory because the specification, plan, and constitution require
deterministic safety, contract, integration, security, lifecycle, data-quality, reproducibility,
and end-to-end validation. Within each user-story phase, write the listed tests first and confirm
that they fail for the intended reason before implementing the story.

**Organization**: Tasks are grouped by user story so each story produces an independently testable
increment. Task order within a phase is tests, persistence, domain rules, interfaces, workers, UI,
and story-level validation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other ready tasks because it changes different files and has no
  dependency on their incomplete work.
- **[Story]**: Maps the task to a user story from `spec.md`.
- Every task names an exact repository-relative file path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the modular-monolith repository, toolchains, deployment skeleton, and test
layout described in `plan.md`.

- [X] T001 Create the planned Python domain, API, worker, web, migration, test, deploy, and isolated MT5 bridge directory skeleton with package markers in `src/traderx/__init__.py` and `apps/mt5_bridge/traderx_mt5_bridge/__init__.py`
- [X] T002 Initialize the Python 3.13 core project and pin FastAPI, Pydantic, SQLAlchemy, Alembic, Celery, HTTPX, Polars, NumPy, SciPy, testing, linting, and typing dependencies in `pyproject.toml`
- [X] T003 [P] Initialize the Node.js 24, Next.js 16, React 19, TypeScript 5.9, TanStack Query, Zod, Tailwind, Vitest, and Playwright workspace in `apps/web/package.json`
- [X] T004 [P] Configure strict TypeScript, module aliases, generated contract types, and test compilation in `apps/web/tsconfig.json`
- [X] T005 [P] Configure Ruff, mypy strict safety-module overrides, pytest markers, coverage, and Hypothesis profiles in `pyproject.toml`
- [X] T006 Configure Alembic to import TraderX metadata and use transaction-safe migrations in `migrations/env.py`
- [X] T007 [P] Define non-secret typed runtime settings and startup validation in `src/traderx/shared/config.py`
- [X] T008 [P] Create the test package layout, shared markers, frozen clocks, and deterministic seeds in `tests/conftest.py`
- [X] T009 [P] Create reusable PostgreSQL, Redis, API, and non-eager Celery test fixtures in `tests/integration/conftest.py`
- [X] T010 [P] Define private-network local services for web, API, worker groups, scheduler, PostgreSQL, Redis, migration, and proxy roles, explicitly excluding the remote MT5 terminal bridge, in `deploy/compose.yaml`
- [X] T011 [P] Add non-root immutable container builds for the Python runtime roles in `deploy/containers/python.Dockerfile`
- [X] T012 [P] Add the production Next.js container build in `deploy/containers/web.Dockerfile`
- [X] T013 [P] Configure the single-origin HTTPS proxy for `/`, `/api/v1`, and `/events` in `deploy/proxy/Caddyfile`
- [X] T014 Configure CI jobs for static checks, migration checks, contract tests, safety tests, integration tests, web tests, and secret scanning in `.github/workflows/ci.yml`

**Checkpoint**: Both toolchains install reproducibly, containers build, migrations initialize, and
the empty test suites execute.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement the persistence, event, API, worker, provider-port, encryption, and web-shell
primitives required by every story.

**CRITICAL**: No user-story implementation starts until this phase is complete.

- [X] T015 [P] Write unit tests for exact decimal conversion, conservative volume rounding, UTC instants, nanosecond event ordering, and IANA reset zones in `tests/unit/shared/test_primitives.py`
- [X] T016 [P] Write integration tests for atomic aggregate, audit, idempotency, and outbox persistence plus consumer deduplication in `tests/integration/test_transactional_outbox.py`
- [X] T017 [P] Write contract tests for RFC 9457 errors, correlation IDs, ETags, `If-Match`, and `Idempotency-Key` semantics in `tests/contract/test_http_common.py`
- [X] T018 [P] Write integration tests for durable job leases, checkpoints, cooperative pause/cancel, bounded retries, and crash redelivery in `tests/integration/test_job_runtime.py`
- [X] T019 Implement opaque identifiers, exact decimal value objects, UTC/nanosecond time types, reason codes, and domain errors in `src/traderx/shared/types.py`
- [X] T020 Implement SQLAlchemy declarative bases, append-only mixins, optimistic versions, naming conventions, and UTC persistence types in `src/traderx/shared/db.py`
- [X] T021 Implement request/task-scoped units of work with explicit transactions and fixed lock-order helpers in `src/traderx/shared/unit_of_work.py`
- [X] T022 [P] Implement RFC 9457 problem mapping and stable domain error codes in `apps/api/traderx_api/middleware/problems.py`
- [X] T023 [P] Implement request, correlation, causation, trace, actor, and idempotency context propagation in `apps/api/traderx_api/middleware/context.py`
- [X] T024 Implement durable idempotency records, canonical request hashing, replay, and conflict handling in `src/traderx/shared/idempotency.py`
- [X] T025 Implement append-only audit records with redacted changes, actor assurance, outcome, reason, and integrity metadata in `src/traderx/audit/model.py`
- [X] T026 Implement CloudEvents-compatible domain envelopes, transactional outbox records, inbox receipts, and per-aggregate ordering in `src/traderx/shared/events.py`
- [X] T027 Implement outbox claiming, dispatch, failure visibility, and idempotent consumer helpers in `apps/worker/traderx_worker/runtime/outbox.py`
- [X] T028 Implement durable background jobs, attempts, leases, checkpoints, progress, and guarded state transitions in `src/traderx/jobs/model.py`
- [X] T029 Implement cooperative worker execution, fencing, cancellation, pause/resume, and retry policy in `apps/worker/traderx_worker/runtime/jobs.py`
- [X] T030 [P] Define broker, market-data, notification, artifact, clock, and calendar protocols, including complete snapshots and optional documented account changes, from the provider contract in `src/traderx/integrations/ports.py`
- [X] T031 [P] Implement AES-256-GCM envelope encryption, key versioning, rotation hooks, and central secret redaction in `src/traderx/integrations/crypto.py`
- [X] T032 Create the foundational idempotency, audit, outbox/inbox, background-job, and artifact-reference schema in `migrations/versions/0001_foundation.py`
- [X] T033 [P] Configure FastAPI application startup, middleware, dependency wiring, OpenAPI metadata, and versioned router registration in `apps/api/traderx_api/main.py`
- [X] T034 [P] Configure Celery queues for monitoring, data, research, paper, notification, and maintenance work with one scheduler in `apps/worker/traderx_worker/runtime/celery_app.py`
- [X] T035 [P] Implement the authenticated application shell, navigation, query provider, error boundary, and accessibility landmarks in `apps/web/src/app/layout.tsx`
- [X] T036 Generate and compile the TypeScript client/types from `specs/001-traderx-core-platform/contracts/http-api.yaml` into `apps/web/src/lib/api/generated.ts`

**Checkpoint**: Foundation is ready; PostgreSQL is the durable truth, asynchronous delivery is
idempotent, the common HTTP contract works, and all user stories may now be developed.

---

## Phase 3: User Story 1 — Establish a Safe Trading Account (Priority: P1) — MVP

**Goal**: Authenticate an owner, connect one verified MT5 primary account, configure
external and stricter internal limits, and show deterministic shared-equity risk and capacity.

**Independent Test**: From a new installation, an owner signs in with MFA, configures one account
and both rule sets through the UI, binds a fresh complete provider snapshot, and sees risk
state/capacity; anonymous and unauthorized access fails, stale/unverified provider data remains in
`LOCKDOWN`, and stricter internal limits block before prop limits.

### Tests for User Story 1

- [X] T037 [P] [US1] Write one-time owner-bootstrap concurrency, password-reset second-proof, recovery-code single-use, assisted-reset authorization, CSRF, TOTP replay, session rotation/revocation, and 30-minute idle/12-hour absolute-expiry tests in `tests/security/test_identity_security.py`
- [X] T038 [P] [US1] Write OWNER/ADMIN/VIEWER authorization-matrix and denied-attempt audit tests in `tests/security/test_rbac_matrix.py`
- [X] T039 [P] [US1] Write account, prop-profile, risk-policy, and Command Center HTTP contract tests in `tests/contract/test_accounts_risk_api.py`
- [X] T040 [P] [US1] Write property tests for stricter-rule precedence, loss monotonicity, reset semantics, and `NORMAL/CAUTION/DEFENSIVE/LOCKDOWN` transitions in `tests/safety/test_risk_properties.py`
- [X] T041 [P] [US1] Write integration tests for account snapshots, exact risk calculations, dynamic `2 -> 1 -> 0` capacity, and circuit-breaker persistence in `tests/integration/test_account_risk_flow.py`
- [X] T042 [P] [US1] Write keyboard-accessible deep-link journeys for `/setup`, `/sign-in`, `/mfa/enroll`, `/mfa/verify`, `/mfa-recovery`, `/password-reset`, session-expiry redirect, account setup, and Command Center access in `apps/web/tests/e2e/safe_account.spec.ts`

### Implementation for User Story 1

- [X] T043 [P] [US1] Implement User, singleton IdentityBootstrapState, AuthSession, MfaFactor, MfaRecoveryCode, PasswordResetChallenge, and AssistedMfaResetRequest models in `src/traderx/identity/model.py`
- [X] T044 [P] [US1] Implement TradingAccount, versioned PropProfile, and versioned RiskPolicy models in `src/traderx/accounts/model.py`
- [X] T045 [P] [US1] Implement AccountSnapshot, RiskSnapshot, RiskDecision, and CircuitBreaker models and state enums in `src/traderx/risk/model.py`
- [X] T046 [US1] Add singleton owner-bootstrap, identity, session, MFA/recovery/reset, account, prop-profile, risk-policy, snapshot, decision, and circuit-breaker tables with concurrency and single-use constraints in `migrations/versions/0002_identity_accounts_risk.py`
- [X] T047 [US1] Implement atomic initial-owner bootstrap, Argon2id passwords, short-lived authentication challenges, opaque MFA-assured sessions, 30-minute idle/12-hour absolute expiry, revocation, and reset-token password replacement without automatic login in `src/traderx/identity/authentication.py`
- [X] T048 [US1] Implement RFC 6238 TOTP enrollment/verification, timestep replay prevention, one-time recovery-code handoff/redemption, authorized assisted reset, fresh-enrollment enforcement, session revocation, and recent-assurance checks in `src/traderx/identity/mfa.py`
- [X] T049 [US1] Implement deny-by-default RBAC policies and high-risk command authorization at the domain boundary in `src/traderx/identity/authorization.py`
- [X] T050 [US1] Implement account setup, one-live-account enforcement, prop-profile versioning, and risk-policy versioning with audit/outbox writes in `src/traderx/accounts/service.py`
- [X] T051 [US1] Implement exact shared-equity loss, drawdown, remaining margin, open risk, risk-state, and capacity calculations in `src/traderx/risk/calculator.py`
- [X] T052 [US1] Implement deterministic circuit-breaker activation, acknowledgement, clearing, and fail-closed capability rules in `src/traderx/risk/circuit_breakers.py`
- [X] T053 [US1] Implement account-snapshot ingestion and transactional risk-snapshot projection in `src/traderx/risk/projection.py`
- [X] T054 [P] [US1] Implement bootstrap-status/bootstrap, login/logout, password-reset request/completion with second proof, MFA enrollment/verification/recovery, assisted-reset, session-list, and revocation routes from `contracts/http-api.yaml` in `apps/api/traderx_api/routes/identity.py`
- [X] T055 [P] [US1] Implement account, prop-profile, risk-policy, risk-snapshot, and circuit-breaker routes with ETags and idempotency in `apps/api/traderx_api/routes/accounts.py`
- [X] T056 [P] [US1] Implement route-specific, state-guarded authentication screens and redirects in `apps/web/src/app/setup/page.tsx`, `apps/web/src/app/sign-in/page.tsx`, `apps/web/src/app/mfa/enroll/page.tsx`, `apps/web/src/app/mfa/verify/page.tsx`, `apps/web/src/app/mfa-recovery/page.tsx`, and `apps/web/src/app/password-reset/page.tsx`
- [X] T057 [P] [US1] Implement trading-account, prop-rule, and internal-risk setup forms with deliberate confirmation in `apps/web/src/features/risk/AccountRiskSetup.tsx`
- [X] T058 [US1] Implement the Command Center account, equity, loss-margin, risk-state, capacity, alert, and freshness panels in `apps/web/src/features/dashboard/CommandCenter.tsx`
- [X] T059 [US1] Wire account snapshots to risk recalculation, dashboard projection, circuit breakers, audit, and outbox consumers in `apps/worker/traderx_worker/tasks/risk.py`

### MT5 Account-Truth Slice

- [X] T060 [P] [US1] Write MT5 bridge create/test/discovered-account/bind HTTP contract tests, including masked enrollment credentials, in `tests/contract/test_broker_integrations_api.py`
- [X] T061 [P] [US1] Write MT5 complete-snapshot, account/server mismatch, investor-mode, and fail-closed adapter tests in `tests/integration/test_mt5_bridge_adapter.py`
- [X] T062 [P] [US1] Write native outbound-EA tests for enrollment identity, investor-mode/trading-disabled proof, login/server match, incomplete snapshot rejection, HTTPS-only transport, and denied terminal trade APIs in `tests/safety/test_mt5_ea_bridge.py`
- [X] T063 [P] [US1] Write end-to-end broker-account-truth tests proving a partial, stale, contradictory, or degraded MT5 snapshot remains non-authoritative and keeps capacity at zero in `tests/integration/test_broker_account_truth.py`
- [X] T064 [P] [US1] Write the accessible MT5 bridge-registration/bind/LOCKDOWN browser journey in `apps/web/tests/e2e/broker_account_setup.spec.ts`
- [X] T065 [P] [US1] Implement broker Integration, credential-version, health-observation, discovered-account, and reconciliation-checkpoint models for `MT5_TERMINAL_BRIDGE` in `src/traderx/integrations/broker_model.py`
- [X] T066 [US1] Add broker integration, selected-account binding, encrypted credential, health, and append-only reconciliation-checkpoint tables in `migrations/versions/0013_broker_account_truth.py`
- [X] T067 [US1] Enforce the MT5-only broker-provider allowlist in `migrations/versions/0015_mt5_only_broker_integrations.py`
- [X] T068 [US1] Implement the server-side native-EA enrollment and narrow account/positions/deals/instruments snapshot receiver with identity verification and fail-closed incomplete-response handling in `src/traderx/integrations/mt5_bridge.py`
- [X] T069 [US1] Implement the outbound-only native MT5 Expert Advisor with local investor authorization, terminal/account verification, read-only snapshot allowlist, HTTPS enrollment, and explicit trade-method absence in `apps/mt5_bridge/mql5/TraderXReadOnlyBridge.mq5`
- [X] T070 [US1] Implement atomic normalized broker snapshot/checkpoint commits, MT5 overlapping-deal reconciliation, and integration-scoped fail-closed outcomes in `src/traderx/integrations/reconciliation.py`
- [X] T071 [US1] Implement authorized create/test/discover/select/bind/disable/reconnect broker integration commands with audit, step-up assurance, and one-primary-account enforcement in `src/traderx/integrations/broker_service.py`
- [X] T072 [P] [US1] Implement the broker integration, test, discovered-account, credential, and primary-account binding operations from `contracts/http-api.yaml` in `apps/api/traderx_api/routes/integrations.py`
- [X] T073 [P] [US1] Implement MT5 account-sync jobs with 15-second target cadence, bounded retry/backoff, health updates, breaker activation, and risk-projection handoff in `apps/worker/traderx_worker/tasks/broker_account_sync.py`
- [X] T074 [P] [US1] Implement MT5 bridge registration, verification status, removal, and LOCKDOWN guidance in `apps/web/src/features/integrations/BrokerAccountIntegration.tsx`

**Checkpoint**: User Story 1 passes independently and is the secure control-plane MVP.

---

## Phase 4: User Story 2 — Select Three Eligible Active Markets (Priority: P1)

**Goal**: Research and human-approve at most one eligible Commodity, Forex pair, and Cryptocurrency
pair using liquidity/data/execution gates before volatility ranking.

**Independent Test**: Seed mixed-quality candidates, run all three category reports, prove every
mandatory failure is excluded before ranking, approve one candidate per category, and prove a new
ranking cannot silently replace it.

### Tests for User Story 2

- [X] T075 [P] [US2] Write broker and market-data adapter contract tests for aliases, specifications, timestamps, duplicate/revision handling, and prohibited live-order capabilities in `tests/contract/test_market_provider_ports.py`
- [X] T076 [P] [US2] Write data-quality tests for freshness, gaps, OHLC invariants, spread, tick/step alignment, contradictory revisions, and quarantine behavior in `tests/data_quality/test_market_quality.py`
- [X] T077 [P] [US2] Write deterministic multi-window volatility, liquidity, cost, eligibility, suitability, and explanation tests in `tests/unit/market_research/test_suitability.py`
- [X] T078 [P] [US2] Write safety tests proving every gate precedes ranking and category/cardinality constraints require human approval in `tests/safety/test_active_market_selection.py`
- [X] T079 [P] [US2] Write market research, Instrument Library, report, and active-market HTTP contract tests in `tests/contract/test_markets_api.py`
- [X] T080 [P] [US2] Write the three-category research, exclusion review, approval, and no-silent-replacement browser journey in `apps/web/tests/e2e/market_selection.spec.ts`

### Implementation for User Story 2

- [X] T081 [P] [US2] Implement Instrument, InstrumentAlias, DataSetManifest, MarketObservation, EconomicEvent, and DataQualityObservation models in `src/traderx/market_data/model.py`
- [X] T082 [P] [US2] Implement MarketResearchRun, CandidateAssessment, suitability-method version, and ActiveMarketAssignment models in `src/traderx/market_research/model.py`
- [X] T083 [US2] Add instrument, alias, dataset, observation, quality, research, assessment, and effective active-assignment tables with one-per-category constraints in `migrations/versions/0003_markets.py`
- [X] T084 [US2] Implement provider-native batch retention, canonical normalization, revisioning, incremental sync, and Parquet manifest hashing in `src/traderx/market_data/ingestion.py`
- [X] T085 [US2] Implement purpose-aware freshness, quality checks, quarantine, and fail-closed status projection in `src/traderx/market_data/quality.py`
- [X] T086 [P] [US2] Implement versioned short/medium/long-window volatility metrics in `src/traderx/market_research/volatility.py`
- [X] T087 [P] [US2] Implement asset-class-aware liquidity, spread, depth, turnover, slippage, and execution metrics in `src/traderx/market_research/liquidity.py`
- [X] T088 [US2] Implement broker, data, liquidity, execution, sizing, gap, hours, and prop-firm eligibility gates in `src/traderx/market_research/eligibility.py`
- [X] T089 [US2] Implement versioned suitability component normalization, weights, score, rank, confidence, and explanation generation in `src/traderx/market_research/suitability.py`
- [X] T090 [US2] Implement category research orchestration and immutable report construction in `src/traderx/market_research/service.py`
- [X] T091 [US2] Implement human-approved activate, deactivate, and replace commands with concurrency, audit, and outbox guarantees in `src/traderx/instruments/active_markets.py`
- [X] T092 [P] [US2] Implement Instrument Library, market research run/report, and active-market routes in `apps/api/traderx_api/routes/markets.py`
- [X] T093 [P] [US2] Implement data synchronization and market research worker tasks with durable progress/cancellation in `apps/worker/traderx_worker/tasks/market_research.py`
- [X] T094 [P] [US2] Implement Instrument Library filters, data status, counts, history, and inactive research affordances in `apps/web/src/features/markets/InstrumentLibrary.tsx`
- [X] T095 [P] [US2] Implement candidate gate evidence, comparable metrics, methodology, ranking, and approval UI in `apps/web/src/features/markets/MarketResearchReport.tsx`
- [X] T096 [US2] Implement active Commodity, Forex, and Cryptocurrency cards with explicit replacement review in `apps/web/src/features/markets/ActiveMarkets.tsx`

**Checkpoint**: User Story 2 independently produces explainable, reproducible, human-approved
active markets without weakening eligibility.

---

## Phase 5: User Story 3 — Build and Validate a Strategy (Priority: P1)

**Goal**: Define immutable deterministic strategies without code and qualify them with realistic,
reproducible historical, unseen-data, robustness, Monte Carlo, and shared-account evidence.

**Independent Test**: Build one strategy from fixtures, run the full historical validation path,
reproduce identical results, reject a fragile/portfolio-unsafe strategy, edit into a new immutable
version, and reject invalid lifecycle transitions.

### Tests for User Story 3

- [X] T097 [P] [US3] Write canonical strategy schema, semantic validation, deterministic interpreter, and golden-trace tests in `tests/unit/strategies/test_strategy_runtime.py`
- [X] T098 [P] [US3] Write immutable version and legal/illegal lifecycle property tests in `tests/safety/test_strategy_lifecycle.py`
- [X] T099 [P] [US3] Write chronological fills, gaps, same-bar ambiguity, costs, exact sizing, stops, targets, and shared-equity backtest tests in `tests/reproducibility/test_backtest_engine.py`
- [X] T100 [P] [US3] Write out-of-sample, walk-forward, parameter-stability, Monte Carlo, and tail-distribution tests in `tests/reproducibility/test_validation_engine.py`
- [X] T101 [P] [US3] Write portfolio signal-competition, correlation, prop breach, and two-position simulation tests in `tests/safety/test_portfolio_simulation.py`
- [X] T102 [P] [US3] Write research, strategy/version, backtest, and validation HTTP contract tests in `tests/contract/test_strategy_validation_api.py`
- [X] T103 [P] [US3] Write the visual strategy, backtest, report, validation, comparison, and immutable-edit browser journey in `apps/web/tests/e2e/strategy_validation.spec.ts`

### Implementation for User Story 3

- [X] T104 [P] [US3] Implement ResearchJobDetail and immutable ResearchExperiment models and manifests in `src/traderx/research/model.py`
- [X] T105 [P] [US3] Implement Strategy and immutable StrategyVersion models with definition hashes and lifecycle state in `src/traderx/strategies/model.py`
- [X] T106 [P] [US3] Implement BacktestRun and ValidationRun evidence models with artifact and reproducibility references in `src/traderx/validation/model.py`
- [X] T107 [US3] Add research, experiment, strategy/version, backtest, validation, metrics, breakdown, and artifact-reference tables in `migrations/versions/0004_strategy_validation.py`
- [X] T108 [US3] Define the versioned canonical strategy schema for regime, timeframes, conditions, filters, stops, targets, invalidation, expiration, and risk in `src/traderx/strategies/schema.py`
- [X] T109 [US3] Implement strategy structural/semantic validation and deterministic compilation in `src/traderx/strategies/compiler.py`
- [X] T110 [US3] Implement the pure strategy state machine with injected clock, calendar, data, portfolio, and execution adapters in `src/traderx/strategies/runtime.py`
- [X] T111 [US3] Implement immutable version creation and evidence-gated lifecycle transition service in `src/traderx/strategies/lifecycle.py`
- [X] T112 [US3] Implement research-job creation, reproducible manifests, candidate/rejection persistence, and result summaries in `src/traderx/research/service.py`
- [X] T113 [P] [US3] Implement chronological event replay, deterministic ordering, signal handling, and portfolio state in `src/traderx/backtesting/engine.py`
- [X] T114 [P] [US3] Implement versioned spread, commission, slippage, gap, partial-fill, session, and ambiguous-bar policies in `src/traderx/backtesting/execution.py`
- [X] T115 [US3] Implement exact sizing/risk integration, stops/targets, trades, equity curves, R, MAE/MFE, and required metrics in `src/traderx/backtesting/report.py`
- [X] T116 [P] [US3] Implement development/validation/out-of-sample splits and rolling walk-forward evaluation in `src/traderx/validation/out_of_sample.py`
- [X] T117 [P] [US3] Implement parameter-neighborhood stability, sensitivity classes, and multiple-trial evidence in `src/traderx/validation/stability.py`
- [X] T118 [P] [US3] Implement deterministic sequence, block/regime bootstrap, cost/gap stress, and tail-risk simulation in `src/traderx/validation/monte_carlo.py`
- [X] T119 [US3] Implement shared-account chronological portfolio simulation with prop rules, risk states, correlation, signal competition, and maximum-two enforcement in `src/traderx/validation/portfolio.py`
- [X] T120 [US3] Implement validation aggregation, `PASS/WARNING/FAIL` evidence, and lifecycle gate decisions in `src/traderx/validation/service.py`
- [X] T121 [P] [US3] Implement research and strategy/version routes with ETags and idempotency in `apps/api/traderx_api/routes/strategies.py`
- [X] T122 [P] [US3] Implement backtest and validation run/report routes returning durable jobs in `apps/api/traderx_api/routes/validation.py`
- [X] T123 [P] [US3] Implement research, backtest, walk-forward, Monte Carlo, and portfolio worker tasks with checkpoints in `apps/worker/traderx_worker/tasks/validation.py`
- [X] T124 [P] [US3] Implement no-code rule groups, condition editors, filters, stops, targets, invalidation, expiry, and risk controls in `apps/web/src/features/strategies/StrategyBuilder.tsx`
- [X] T125 [P] [US3] Implement immutable version history, comparison, lifecycle status, and unmet-prerequisite UI in `apps/web/src/features/strategies/StrategyVersions.tsx`
- [X] T126 [P] [US3] Implement research/backtest configuration, durable job progress, cancel/retry, and results UI in `apps/web/src/features/strategies/ResearchBacktest.tsx`
- [X] T127 [US3] Implement metrics, breakdowns, equity/trade evidence, validation windows, distributions, and portfolio report UI in `apps/web/src/features/strategies/ValidationReport.tsx`

**Checkpoint**: User Story 3 independently delivers reproducible strategy evidence; no fragile,
failed, mutable, or portfolio-unsafe version progresses.

---

## Phase 6: User Story 4 — Paper Trade and Approve a Strategy (Priority: P1)

**Goal**: Run validated strategies on current data with simulated execution, compare evidence, and
require an explicit authorized human decision before live eligibility.

**Independent Test**: Paper trade a qualified fixture strategy, prove duration/trade count alone is
insufficient, route divergence to review, end success at `AWAITING_APPROVAL`, and approve only with
current evidence and recent authorized MFA.

### Tests for User Story 4

- [X] T128 [P] [US4] Write historical/paper/live-adapter golden-trace parity and simulated-fill tests in `tests/reproducibility/test_runtime_parity.py`
- [X] T129 [P] [US4] Write paper eligibility, combined evidence threshold, divergence, and no-auto-promotion safety tests in `tests/safety/test_paper_promotion.py`
- [X] T130 [P] [US4] Write approval authorization, step-up MFA, stale evidence, idempotency, concurrency, and audit tests in `tests/security/test_strategy_approval.py`
- [X] T131 [P] [US4] Write paper run, comparison, and strategy approval HTTP contract tests in `tests/contract/test_paper_approval_api.py`
- [X] T132 [P] [US4] Write the paper portfolio, evidence comparison, and deliberate approval browser journey in `apps/web/tests/e2e/paper_approval.spec.ts`

### Implementation for User Story 4

- [X] T133 [P] [US4] Implement PaperRun, simulated Position/Execution references, comparison, criteria, and disposition models in `src/traderx/paper/model.py`
- [X] T134 [P] [US4] Implement append-only StrategyApproval decision and assurance snapshot model in `src/traderx/strategies/approval_model.py`
- [X] T135 [US4] Add paper run, simulated trade, promotion criteria, comparison, and strategy approval tables in `migrations/versions/0005_paper_approval.py`
- [X] T136 [US4] Implement current-data simulated entry, exit, stop, target, cost, and exact risk behavior using the canonical runtime in `src/traderx/paper/engine.py`
- [X] T137 [US4] Implement multi-factor paper eligibility and historical-versus-paper divergence evaluation in `src/traderx/paper/evidence.py`
- [X] T138 [US4] Implement paper orchestration, portfolio projection, journaling, checkpoints, and terminal disposition in `src/traderx/paper/service.py`
- [X] T139 [US4] Implement audited `APPROVE_LIVE`, `REJECT`, and `RETURN_TO_RESEARCH` commands with fresh-evidence and recent-MFA checks in `src/traderx/strategies/approval.py`
- [X] T140 [P] [US4] Implement paper run, position, history, performance, comparison, and promotion routes in `apps/api/traderx_api/routes/paper.py`
- [X] T141 [P] [US4] Implement strategy approval review/decision route with ETag and idempotency preconditions in `apps/api/traderx_api/routes/approvals.py`
- [X] T142 [P] [US4] Implement current-data paper evaluation and checkpointed lifecycle worker tasks in `apps/worker/traderx_worker/tasks/paper.py`
- [X] T143 [P] [US4] Implement paper strategies, positions, history, and performance UI in `apps/web/src/features/paper/PaperTrading.tsx`
- [X] T144 [US4] Implement backtest-versus-paper evidence, promotion eligibility, and step-up approval UI in `apps/web/src/features/paper/ApprovalReview.tsx`

**Checkpoint**: User Story 4 independently proves paper evidence cannot promote itself and only an
authorized human can grant current live eligibility.

---

## Phase 7: User Story 5 — Receive a Risk-Approved Recommendation (Priority: P1)

**Goal**: Rank live opportunities and issue a complete expiring recommendation only after exact
shared-account portfolio risk authorizes it.

**Independent Test**: Evaluate prepared active markets and live-approved strategies under zero,
one, and two-position states; prove high scores cannot override safety, second positions may be
reduced/blocked, every third is blocked, and missing critical data produces no recommendation.

### Tests for User Story 5

- [X] T145 [P] [US5] Write opportunity score, state, ranking, and live-eligibility tests in `tests/unit/opportunities/test_opportunity_engine.py`
- [X] T146 [P] [US5] Write exact volume, tick/step rounding, cross-currency conversion, and never-increase-risk property tests in `tests/safety/test_position_sizing.py`
- [X] T147 [P] [US5] Write zero/one/two/third-position, correlation, common exposure, loss margin, Risk Manager veto, and lockdown tests in `tests/safety/test_live_capacity.py`
- [X] T148 [P] [US5] Write missing/stale/contradictory data and failed dependency no-recommendation tests in `tests/safety/test_recommendation_fail_closed.py`
- [X] T149 [P] [US5] Write opportunity and complete/expired recommendation HTTP contract tests in `tests/contract/test_opportunities_api.py`
- [X] T150 [P] [US5] Write the ranking, pass/reduce/block reasons, complete recommendation, and expiration browser journey in `apps/web/tests/e2e/opportunities.spec.ts`

### Implementation for User Story 5

- [X] T151 [P] [US5] Implement immutable Opportunity, score components, evidence, state, and expiry models in `src/traderx/opportunities/model.py`
- [X] T152 [P] [US5] Implement immutable Recommendation, exact levels/risk/volume, invalidation, and lifecycle models in `src/traderx/opportunities/recommendation_model.py`
- [X] T153 [US5] Add opportunity, score component, risk decision link, recommendation, target, and expiry tables in `migrations/versions/0006_opportunities.py`
- [X] T154 [US5] Implement live strategy eligibility, current regime/signal evaluation, evidence construction, and first-class no-trade states in `src/traderx/opportunities/evaluator.py`
- [X] T155 [US5] Implement explainable opportunity components and ranking independent of risk authorization in `src/traderx/opportunities/ranking.py`
- [X] T156 [US5] Implement rolling correlation, currency/macro common-factor exposure, marginal risk, and second-position assessment in `src/traderx/portfolio/exposure.py`
- [X] T157 [US5] Implement exact account/instrument-aware sizing with conservative minimum/step rounding and conversion-quality checks in `src/traderx/risk/sizing.py`
- [X] T158 [US5] Implement transactional Risk Manager `PASS/PASS_REDUCED/BLOCKED` decisions with server-side recomputation and hard capacity limit in `src/traderx/risk/manager.py`
- [X] T159 [US5] Implement complete recommendation issuance, reason traces, invalidation, expiry, and withdrawal without any order capability in `src/traderx/opportunities/recommendations.py`
- [X] T160 [P] [US5] Implement ranked opportunity and recommendation routes in `apps/api/traderx_api/routes/opportunities.py`
- [X] T161 [P] [US5] Implement scheduled live-strategy evaluation, expiry, and risk-decision worker tasks in `apps/worker/traderx_worker/tasks/opportunities.py`
- [X] T162 [P] [US5] Implement the three-category ranked opportunity board with score/risk separation and no-trade states in `apps/web/src/features/opportunities/OpportunityBoard.tsx`
- [X] T163 [US5] Implement complete recommendation detail, sizing evidence, rationale, invalidation, freshness, and expiry UI in `apps/web/src/features/opportunities/RecommendationPanel.tsx`

**Checkpoint**: User Story 5 independently delivers safe decision support, never an execution path.

---

## Phase 8: User Story 6 — Manually Execute and Monitor a Trade (Priority: P1)

**Goal**: Consume verified MT5 account truth to detect manually created broker positions,
classify and include them in shared risk, freeze recommended trade theses, and monitor evidence
without executing orders.

**Independent Test**: Reconcile a matching and discretionary fixture position, prove both affect
risk, correct classification, monitor an immutable thesis through health states, and inspect the
code/contract to prove no live-order operation exists.

### Tests for User Story 6

- [X] T164 [P] [US6] Write MT5 poll reconciliation tests for duplicate, out-of-order, overlapping-deal window gap, partial-fill, correction, and contradiction cases in `tests/integration/test_broker_reconciliation.py`
- [X] T165 [P] [US6] Write matching, discretionary classification, correction, and immediate shared-risk tests in `tests/integration/test_position_classification.py`
- [X] T166 [P] [US6] Write frozen thesis immutability and thesis-based health/guidance tests in `tests/safety/test_trade_monitoring.py`
- [X] T167 [P] [US6] Write static and runtime tests proving broker ports, routes, workers, and adapters expose no live-order submission path in `tests/safety/test_no_live_execution.py`
- [X] T168 [P] [US6] Write position, classification, thesis, and monitoring HTTP contract tests in `tests/contract/test_positions_api.py`
- [X] T169 [P] [US6] Write the detected recommended/discretionary position and thesis-monitoring browser journey in `apps/web/tests/e2e/live_monitoring.spec.ts`

### Implementation for User Story 6

- [X] T170 [P] [US6] Implement Position, TradeExecution, reconciliation state, classification, and provider revision models in `src/traderx/monitoring/position_model.py`
- [X] T171 [P] [US6] Implement immutable TradeThesis and append-only MonitoringObservation models in `src/traderx/monitoring/thesis_model.py`
- [X] T172 [US6] Add live position, fill/deal, classification history, thesis, and monitoring observation tables in `migrations/versions/0007_monitoring.py`
- [X] T173 [US6] Implement normalized MT5 poll consumption, authoritative reconciliation, overlapping-deal window handling, deduplication, and contradiction detection in `src/traderx/monitoring/reconciliation.py`
- [X] T174 [US6] Implement recommendation matching, confidence, discretionary fallback, and audited user correction in `src/traderx/monitoring/matching.py`
- [X] T175 [US6] Wire every live position and fill projection into transactional account/risk recalculation in `src/traderx/monitoring/risk_projection.py`
- [X] T176 [US6] Implement one-time frozen thesis creation from matched recommendation evidence in `src/traderx/monitoring/thesis.py`
- [X] T177 [US6] Implement thesis-versus-market evaluation and `STRONG/HEALTHY/WATCH/WEAKENING/INVALIDATED` guidance in `src/traderx/monitoring/monitor.py`
- [X] T178 [P] [US6] Implement position list, classification correction, thesis, and monitoring routes in `apps/api/traderx_api/routes/positions.py`
- [X] T179 [P] [US6] Implement priority consumption of MT5 account-sync results and live-monitoring worker loops in `apps/worker/traderx_worker/tasks/monitoring.py`
- [X] T180 [P] [US6] Implement open/history position views, match confidence, and classification correction UI in `apps/web/src/features/trades/Positions.tsx`
- [X] T181 [US6] Implement immutable original-thesis and append-only health timeline UI in `apps/web/src/features/trades/TradeMonitor.tsx`

**Checkpoint**: User Story 6 independently detects and monitors manual execution while retaining
the constitutional negative capability for real-money orders.

---

## Phase 9: User Story 7 — Journal Outcomes and Learn (Priority: P2)

**Goal**: Automatically journal all supported trade types, accept behavioral context, analyze
financial and R performance, and create research proposals without changing strategies.

**Independent Test**: Close recommended, discretionary, and paper fixture trades, annotate them,
filter analytics across required dimensions, and produce a research hypothesis that leaves the
source strategy unchanged.

### Tests for User Story 7

- [X] T182 [P] [US7] Write journal projection, correction provenance, financial P&L, R-multiple, and all-trade-type tests in `tests/integration/test_journal_projection.py`
- [X] T183 [P] [US7] Write annotation, protected attachment, analytics dimension, and hypothesis non-mutation tests in `tests/integration/test_journal_learning.py`
- [X] T184 [P] [US7] Write journal entry, annotation, attachment, analytics, and research-proposal HTTP contract tests in `tests/contract/test_journal_api.py`
- [X] T185 [P] [US7] Write the journal annotation, screenshot, filtering, comparison, and hypothesis browser journey in `apps/web/tests/e2e/journal.spec.ts`

### Implementation for User Story 7

- [X] T186 [P] [US7] Implement JournalEntry, sourced correction, annotation, attachment, and review models in `src/traderx/journal/model.py`
- [X] T187 [US7] Add journal entry, annotation version, protected attachment, review, and research-proposal tables in `migrations/versions/0008_journal.py`
- [X] T188 [US7] Implement automatic recommended, discretionary, and paper journal projection with exact P&L and R in `src/traderx/journal/projector.py`
- [X] T189 [US7] Implement annotation supersession, attachment authorization, checksum, and metadata service in `src/traderx/journal/service.py`
- [X] T190 [US7] Implement performance aggregation by instrument, asset class, version, time, direction, risk, regime, entry quality, and behavior in `src/traderx/journal/analytics.py`
- [X] T191 [US7] Implement evidence-linked research proposal creation that cannot mutate or promote a strategy in `src/traderx/journal/hypotheses.py`
- [X] T192 [P] [US7] Implement journal entry, annotation, attachment, analytics, and proposal routes in `apps/api/traderx_api/routes/journal.py`
- [X] T193 [P] [US7] Implement trade-close journal and rolling analytics worker consumers in `apps/worker/traderx_worker/tasks/journal.py`
- [X] T194 [P] [US7] Implement journal list/detail, automatic evidence, annotations, and protected attachment UI in `apps/web/src/features/journal/Journal.tsx`
- [X] T195 [US7] Implement performance filters, R/financial comparisons, behavior analysis, and research proposal UI in `apps/web/src/features/journal/JournalAnalytics.tsx`

**Checkpoint**: User Story 7 independently produces durable learning without rewriting history.

---

## Phase 10: User Story 8 — Replace and Reactivate Markets Without Losing Knowledge (Priority: P2)

**Goal**: Replace active instruments without deletion and reactivate them through incremental data
refresh, evidence-staleness assessment, selective revalidation, and human approval.

**Independent Test**: Replace a fixture instrument with complete knowledge, verify every record
remains, create a later data gap, reactivate, and prove stale strategies cannot become live until
the recommended refresh/validation/approval path completes.

### Tests for User Story 8

- [X] T196 [P] [US8] Write migration and repository tests proving instrument references use preservation rules and no replacement path cascade-deletes evidence in `tests/integration/test_instrument_retention.py`
- [X] T197 [P] [US8] Write incremental gap detection, alias continuity, staleness classification, selective revalidation, and no-auto-reactivation tests in `tests/safety/test_instrument_reactivation.py`
- [X] T198 [P] [US8] Write replacement recommendation, history, reactivation plan, and approval HTTP contract tests in `tests/contract/test_market_rotation_api.py`
- [X] T199 [P] [US8] Write the replacement comparison, retained knowledge, reactivation, and revalidation browser journey in `apps/web/tests/e2e/market_rotation.spec.ts`

### Implementation for User Story 8

- [X] T200 [US8] Add explicit restrictive-delete constraints and effective-history indexes for instrument knowledge in `migrations/versions/0009_instrument_retention.py`
- [X] T201 [US8] Implement periodic current-versus-candidate suitability comparison and explainable replacement recommendation in `src/traderx/market_research/replacement.py`
- [X] T202 [US8] Implement existing coverage lookup, alias reconciliation, missing-interval planning, and incremental refresh in `src/traderx/instruments/reactivation.py`
- [X] T203 [US8] Implement `CURRENT/REVALIDATION_REQUIRED/STALE/LEGACY` evidence classification and selective validation plan generation in `src/traderx/strategies/staleness.py`
- [X] T204 [US8] Implement reactivation orchestration that loads preserved knowledge and ends in human approval rather than live status in `src/traderx/instruments/reactivation_service.py`
- [X] T205 [P] [US8] Implement replacement research, assignment history, knowledge summary, and reactivation plan routes in `apps/api/traderx_api/routes/market_rotation.py`
- [X] T206 [P] [US8] Implement scheduled replacement research, data-gap sync, and revalidation-plan worker tasks in `apps/worker/traderx_worker/tasks/market_rotation.py`
- [X] T207 [P] [US8] Implement current/candidate score comparison and deliberate replacement UI in `apps/web/src/features/markets/MarketReplacement.tsx`
- [X] T208 [US8] Implement retained-knowledge inventory, data gaps, staleness, and reactivation workflow UI in `apps/web/src/features/markets/InstrumentReactivation.tsx`

**Checkpoint**: User Story 8 independently proves that market rotation never destroys or silently
reactivates governed evidence.

---

## Phase 11: User Story 9 — Operate and Audit TraderX from the UI (Priority: P2)

**Goal**: Manage integrations, jobs, notifications, strategy health, system health, secrets, and
audit evidence entirely through authenticated screens.

**Independent Test**: An authorized user connects/tests/disables/reconnects/rotates an integration,
manages a checkpointed job, configures delivery, triggers failures and recovery, and reviews
complete redacted audit history without direct infrastructure access.

### Tests for User Story 9

- [X] T209 [P] [US9] Write envelope-encryption, rotation, write-only presentation, and log/telemetry/audit redaction tests in `tests/security/test_secret_management.py`
- [X] T210 [P] [US9] Write integration health, capability allowlist, official-source-only, test/disable/reconnect, and failure recovery tests in `tests/integration/test_integration_operations.py`
- [X] T211 [P] [US9] Write outbox notification routing, preference, deduplication, bounded retry, ambiguous timeout, and durable critical-web-inbox tests in `tests/integration/test_notifications.py`
- [X] T212 [P] [US9] Write job state/action, safe checkpoint cancellation, browser independence, progress stream, and retry contract tests in `tests/integration/test_job_operations.py`
- [X] T213 [P] [US9] Write append-only audit, mandatory audit failure, high-risk before/after, and authorized-read tests in `tests/security/test_audit_integrity.py`
- [X] T214 [P] [US9] Write integrations, jobs, notifications, audit, event stream, and health HTTP contract tests in `tests/contract/test_operations_api.py`
- [X] T215 [P] [US9] Write the UI-only integration, credential rotation, job control, notification preference, health, and audit browser journey in `apps/web/tests/e2e/system_operations.spec.ts`

### Implementation for User Story 9

- [X] T216 [P] [US9] Implement the approved-provider registry, non-broker integration configuration, and capability-policy extension around the broker core from T065 in `src/traderx/integrations/registry.py`
- [X] T217 [P] [US9] Implement NotificationEvent, user preference, routed notification, and delivery-attempt models in `src/traderx/notifications/model.py`
- [X] T218 [P] [US9] Implement StrategyHealthObservation and suspension recommendation/state models in `src/traderx/strategies/health_model.py`
- [X] T219 [US9] Add notification/preference/delivery and strategy-health tables, plus any non-broker integration extension tables, in `migrations/versions/0010_operations.py`
- [X] T220 [US9] Extend the broker integration commands from T071 with UI-managed enable/disable/reconnect/rotate and implement equivalent approved non-broker operations with step-up assurance and audit in `src/traderx/integrations/service.py`
- [X] T221 [US9] Implement health aggregation for integrations, workers, queues, database, data freshness, and safety capability impact in `src/traderx/integrations/health.py`
- [X] T222 [US9] Implement channel-independent notification routing, severity/preferences, web inbox, deduplication, and bounded delivery retries in `src/traderx/notifications/router.py`
- [X] T223 [US9] Implement rolling live strategy health, comparison ranges, watch/suspend recommendation, and suspension enforcement in `src/traderx/strategies/health.py`
- [X] T224 [P] [US9] Extend the broker integration routes from T072 with masked lifecycle and credential-rotation responses, ETags, idempotency, and approved non-broker operations in `apps/api/traderx_api/routes/integrations.py`
- [X] T225 [P] [US9] Implement durable job list/detail/control and authenticated SSE progress routes in `apps/api/traderx_api/routes/jobs.py`
- [X] T226 [P] [US9] Implement notification inbox/preference and channel test routes in `apps/api/traderx_api/routes/notifications.py`
- [X] T227 [P] [US9] Implement authorized audit search/detail and redacted system-health routes in `apps/api/traderx_api/routes/operations.py`
- [X] T228 [P] [US9] Implement email, Telegram, and durable web delivery adapters in `src/traderx/notifications/providers.py`
- [X] T229 [P] [US9] Implement notification delivery, health polling, strategy-health, and maintenance worker tasks in `apps/worker/traderx_worker/tasks/operations.py`
- [X] T230 [P] [US9] Compose the broker-account UI from T074 with integration cards, write-only credential rotation, test/enable/disable/reconnect actions, and health UI in `apps/web/src/features/integrations/Integrations.tsx`
- [X] T231 [P] [US9] Implement job state, progress, valid actions, results, failures, and SSE/poll fallback UI in `apps/web/src/features/system/Jobs.tsx`
- [X] T232 [P] [US9] Implement notification inbox, severity, channel preferences, delivery status, and channel test UI in `apps/web/src/features/notifications/Notifications.tsx`
- [X] T233 [US9] Implement system/integration/data health, strategy health, circuit-breaker visibility, and authorized audit UI in `apps/web/src/features/system/SystemControl.tsx`

**Checkpoint**: User Story 9 independently proves ordinary operation, visibility, secret handling,
and audit are available through authenticated UI workflows.

---

## Phase 12: Polish and Cross-Cutting Release Gates

**Purpose**: Prove full-system constitutional compliance, resilience, performance, usability,
security, deployment safety, and recoverability.

- [X] T234 [P] Add static source and contract guards against real-money order operations, scraping providers, unapproved integration capabilities, and MT5 trade-method imports in `tests/safety/test_constitutional_negative_capabilities.py`
- [X] T235 [P] Add end-to-end constitutional invariant scenarios for eligibility order, three categories, dynamic capacity, Risk Manager veto, lifecycle gates, manual execution, and retained knowledge in `tests/e2e/test_constitutional_invariants.py`
- [X] T236 [P] Add cross-module property/state-machine tests for concurrent high-risk commands, stale ETags, duplicate events, and aggregate ordering in `tests/safety/test_concurrency_invariants.py`
- [X] T237 [P] Add migration forward/rollback rehearsal and governed-evidence preservation checks in `tests/integration/test_migrations.py`
- [X] T238 [P] Add encrypted backup, restore, outbox/job recovery, and audit/evidence checksum validation in `tests/integration/test_backup_restore.py`
- [X] T239 [P] Add performance scenarios for dashboard latency, risk decisions, broker visibility, notifications, job progress, and large market/research datasets in `tests/performance/test_success_criteria.py`
- [X] T240 [P] Add browser accessibility, responsive layout, keyboard flow, color contrast, error recovery, and usability-success checks in `apps/web/tests/e2e/accessibility.spec.ts`
- [X] T241 [P] Add authentication abuse, session fixation, CSRF, authorization bypass, dependency, static security, and baseline dynamic scan configuration in `tests/security/test_application_hardening.py`
- [X] T242 Implement structured redacted logs, OpenTelemetry traces/metrics, correlation propagation, queue/data freshness metrics, and alert hooks in `src/traderx/shared/observability.py`
- [X] T243 Harden containers with non-root users, read-only filesystems, health/readiness probes, resource limits, private networks, and Docker secrets in `deploy/compose.production.yaml`
- [X] T244 Implement one-shot migration, encrypted off-host backup, restore verification, and key-rotation operator procedures in `deploy/operations/runbook.md`
- [ ] T245 Reconcile the generated server/client implementation with the OpenAPI, domain-event, and provider contracts and document compatibility in `specs/001-traderx-core-platform/contracts/compatibility-report.md`
- [ ] T246 Execute every scenario in the validation guide and record evidence, deviations, and outcomes in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T247 Map all 105 functional requirements and 22 success criteria to implementation and passing evidence in `specs/001-traderx-core-platform/traceability.md`
- [ ] T248 Perform the pre-production Constitution Check and document that all governed rules and release-blocking tests pass in `specs/001-traderx-core-platform/constitution-compliance.md`
- [X] T249 Update installation, owner bootstrap, UI-only operations, safety boundaries, and manual execution guidance in `README.md`

**Checkpoint**: The full TraderX V1 design is implemented, traceable, recoverable, and eligible for
deliberate production review only when every constitutional gate passes.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: No dependencies; starts immediately.
- **Phase 2 — Foundational**: Depends on Setup and blocks every user story.
- **US1 — Safe Trading Account**: Starts after Foundational and establishes production account/risk
  truth through a verified MT5 terminal-bridge account used by later live workflows.
- **US2 — Active Markets**: Starts after Foundational; uses account/prop fixtures independently,
  then uses the verified US1 broker account for production eligibility.
- **US3 — Strategy Validation**: Starts after Foundational; uses instrument/account fixtures
  independently, then integrates with US1 and US2.
- **US4 — Paper and Approval**: Depends on US3 strategy runtime and validation evidence; uses US1
  authorization and risk in production.
- **US5 — Recommendations**: Depends on US1 risk, US2 active markets, US3 live strategy runtime,
  and US4 human approval.
- **US6 — Manual Monitoring**: Depends on US1 account/risk and its MT5 account-truth slice,
  plus US5 recommendation structures; its discretionary-position path remains independently
  testable with broker fixtures.
- **US7 — Journal and Learning**: Depends on trade/paper outputs from US4 and US6; journal projection
  remains independently testable with fixture events.
- **US8 — Market Rotation**: Depends on US2 instrument/selection and US3 validation history;
  production reactivation also uses US4 approval.
- **US9 — UI Operations and Audit**: Extends the US1 broker integration control plane with audit,
  jobs, notifications, and cross-system health; each operations flow remains fixture-testable.
- **Phase 12 — Polish**: Depends on every story included in the intended release.

### User Story Dependency Graph

```text
Setup -> Foundation
Foundation -> US1 (MT5 bridge account truth)
Foundation -> US2
Foundation -> US3
US3 -> US4
US1 + US2 + US3 + US4 -> US5
US1 + US5 -> US6
US4 + US6 -> US7
US2 + US3 + US4 -> US8
US1 -> US9, then integrate US1..US8 events and health
US1..US9 -> Polish / Production Review
```

### Within Each User Story

1. Write all story tests first and verify they fail for missing behavior.
2. Add models and migrations before persistence-dependent services.
3. Implement deterministic domain rules before routes, workers, or UI.
4. Implement routes/workers/UI in parallel only after their domain dependencies are ready.
5. Run the story's unit, contract, integration, safety/security, and browser tests at its checkpoint.

## Parallel Opportunities

- Setup tasks marked `[P]` may run concurrently after T001/T002 prerequisites as applicable.
- Foundation test tasks T015–T018 are parallel; middleware, provider protocols, encryption, API,
  worker, and web shell work split across distinct files once their required primitives exist.
- All tests marked `[P]` within a story may be authored concurrently before implementation.
- Models marked `[P]` within a story may be created concurrently before that story's migration.
- After domain services exist, API routes, worker tasks, and web components marked `[P]` may proceed
  concurrently.
- US1, US2, US3, and the foundation-dependent portion of US9 can be staffed in parallel using
  fixtures; production integration follows the dependency graph.
- US7 and US8 can run in parallel after their respective US4/US6 and US2/US3 prerequisites.
- Cross-cutting release tests T234–T241 can be developed concurrently against the integrated build.

## Parallel Execution Examples

### User Story 1

```text
Parallel account/risk tests: T037, T038, T039, T040, T041, T042
Parallel broker tests: T060, T061, T062, T063, T064
Parallel models: T043, T044, T045, T065
Parallel interfaces after domain services: T054, T055, T056, T057, T072, T073, T074
```

### User Story 2

```text
Parallel tests: T075, T076, T077, T078, T079, T080
Parallel models: T081, T082
Parallel interfaces after market services: T092, T093, T094, T095
```

### User Story 3

```text
Parallel tests: T097, T098, T099, T100, T101, T102, T103
Parallel models: T104, T105, T106
Parallel validators after runtime: T116, T117, T118
Parallel interfaces after validation service: T121, T122, T123, T124, T125, T126
```

### User Story 4

```text
Parallel tests: T128, T129, T130, T131, T132
Parallel models: T133, T134
Parallel interfaces after services: T140, T141, T142, T143
```

### User Story 5

```text
Parallel tests: T145, T146, T147, T148, T149, T150
Parallel models: T151, T152
Parallel interfaces after recommendation service: T160, T161, T162
```

### User Story 6

```text
Parallel tests: T164, T165, T166, T167, T168, T169
Parallel models: T170, T171
Parallel interfaces after monitor service: T178, T179, T180
```

### User Story 7

```text
Parallel tests: T182, T183, T184, T185
Parallel API, worker, and primary UI after services: T192, T193, T194
```

### User Story 8

```text
Parallel tests: T196, T197, T198, T199
Parallel API, worker, and replacement UI after services: T205, T206, T207
```

### User Story 9

```text
Parallel tests: T209, T210, T211, T212, T213, T214, T215
Parallel models: T216, T217, T218
Parallel routes/adapters/UI after services: T224, T225, T226, T227, T228, T229, T230, T231, T232
```

## Implementation Strategy

### MVP First: Secure Control Plane

1. Complete Phase 1 Setup.
2. Complete Phase 2 Foundational prerequisites.
3. Complete US1 through T074, including one MT5 demo account-truth path.
4. Stop and run every US1 test and the account/risk and broker portions of `quickstart.md`.
5. Demonstrate authenticated UI-only account/risk control with verified snapshots; do not describe
   it as trading-ready.

### Incremental Delivery

1. **Secure control plane**: Setup + Foundation + US1.
2. **Market intelligence**: US2.
3. **Strategy research platform**: US3.
4. **Paper evidence and promotion**: US4.
5. **Live decision support**: US5.
6. **Manual position monitoring**: US6.
7. **Journal and learning**: US7.
8. **Market rotation and knowledge reuse**: US8.
9. **Complete UI operations and audit**: US9.
10. **Production eligibility**: Phase 12 only after all desired stories pass their checkpoints.

### Parallel Team Strategy

After the shared foundation, separate teams may build US1, US2, US3, and the independent US9
operations shell with contract fixtures. Teams then converge in dependency order for US4–US8.
No team may duplicate Risk Manager, sizing, strategy runtime, authorization, or audit rules in the
web application or an integration adapter.

## Notes

- `[P]` means the task is parallel only after its stated phase dependencies are satisfied.
- Every user-story task carries exactly one `[USn]` label; Setup, Foundational, and Polish tasks do
  not carry story labels.
- Test tasks precede implementation and must fail before the behavior exists.
- A task that affects financial safety is incomplete until its deterministic rule, evidence,
  authorization, failure mode, audit event, and test oracle are all present.
- Commit after each task or coherent task group, and run the story checkpoint before advancing.
- Do not add automatic real-money execution, a third live position, a fourth active category,
  strategy auto-promotion, AI risk authority, scraping, or evidence deletion without a formal
  constitutional amendment.

---

## Phase 13: Convergence

**Purpose**: Close the verified gaps between the governed TraderX design and the current working
identity/account/MT5 slice. The existing user-story tasks remain the detailed implementation
breakdown; these tasks establish the required convergence order and prevent the present route and
UI scaffolding from being mistaken for complete product functionality.

- [X] T250 Reconcile the MT5-only broker product decision, remove retired-broker scope, and preserve investor-mode, read-only, fail-closed, and manual-execution constraints in `specs/001-traderx-core-platform/traceability.md`
- [X] T251 Protect every operational router with authenticated-session and deny-by-default role checks and prove anonymous/unauthorized denials and audit evidence in `tests/security/test_operational_route_access.py`
- [X] T252 Compose the shared authenticated Command Center shell with account/risk, integration health, markets, opportunities, alerts, and implemented workspaces without creating a second product surface in `apps/web/src/app/layout.tsx`
- [ ] T253 Close the persisted, authorized US2 market-intelligence flow and record evidence for eligibility-before-ranking, three explicit selections, and no silent replacement in `specs/001-traderx-core-platform/traceability.md`
- [ ] T254 Close the persisted US3 no-code strategy and reproducible validation flow and record its lifecycle and browser evidence in `specs/001-traderx-core-platform/traceability.md`
- [ ] T255 Close the US4 current-data paper, evidence comparison, `AWAITING_APPROVAL`, and step-up human decision flow and record proof of no automatic promotion in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T256 Close the US5 deterministic opportunity, shared-account Risk Manager, conservative sizing, expiring recommendation, and visible `NO TRADE`/`BLOCKED` flow and record no-live-order proof in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T257 Close the US6 read-only MT5 position reconciliation, matching/classification, immediate risk projection, frozen-thesis monitoring, and correction flow and record evidence in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T258 Close the US7/US8 journal, analytics, non-mutating hypothesis, retained knowledge, and controlled reactivation/replacement flows and record evidence in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T259 Close the US9 durable jobs, integration lifecycle/health, notifications, strategy health, redacted audit, and system-health flows and record UI-only operation evidence in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T260 Execute and record SC-001 through SC-022 production-readiness evidence, including constitutional/concurrency, migration/restore, performance/accessibility, contract/traceability, and Vitest-warning closure in `specs/001-traderx-core-platform/quickstart-results.md`

## Phase 14: Convergence

- [ ] T261 Restore the authorized Account & Risk workspace inside the current Command Center after activation with visible account/profile/policy state, ETags, deliberate effect/confirmation/reason, MFA/role checks, audit evidence, and clear result states in `apps/web/src/features/risk/AccountRiskSetup.tsx`

---

## Phase 15: Market-Research Amendment Foundation (Shared Infrastructure)

**Purpose**: Add the reviewed provider catalogue, versioned source policies, durable scheduling,
and advisory-model persistence required by both US2 market selection and US9 integration
operations.

**Critical**: Complete this phase before starting the amended US2 or US9 tasks. The migration and
catalogue must not mark a provider usable until its entitlement, credential, capability, mapping,
freshness, and qualification states pass.

- [X] T262 [P] Extend the provider contracts with reviewed market-data capabilities, source semantics, bounded retry classifications, entitlement evidence, and the non-authoritative `LlmAnalysisPort` in `src/traderx/integrations/ports.py`
- [X] T263 [P] Add `ProviderCatalogueEntry`, `FreshnessPolicyVersion`, `RetryPolicyVersion`, catalogue-bound integration configuration, credential version, and capability-health persistence models in `src/traderx/integrations/model.py`
- [X] T264 [P] Extend dataset manifests, observations, and aliases with venue, capability, actual/proxy/unavailable semantics, mapping revision, entitlement, source times, freshness-policy version, conflict state, and immutable raw-evidence references in `src/traderx/market_data/model.py`
- [X] T265 [P] Add the global model configuration, research schedule, occurrence, coordinated parent run, category-run source manifest, policy/model pins, and LLM attempt models in `src/traderx/market_research/model.py`
- [X] T266 Create the provider catalogue, versioned policies, integration extensions, source evidence, model configuration, schedule/occurrence, coordinated run, and LLM attempt tables with unique occurrence and exactly-three-category constraints in `migrations/versions/0023_market_research_automation.py`
- [X] T267 Seed deny-by-default MT5, CME Group, Cboe FX Spot, Coinbase Exchange, OpenAI Responses, and Anthropic Messages catalogue profiles plus disabled verification-only profiles and versioned freshness/retry defaults in `src/traderx/integrations/registry.py`
- [X] T268 [P] Add typed provider endpoint, timeout, retry, retention, and scheduler bounds while rejecting arbitrary production source or model URLs in `src/traderx/shared/config.py`
- [X] T269 Implement canonical source-evidence construction, capability-aware freshness evaluation, actual/proxy/unavailable labelling, and conflict quarantine inputs in `src/traderx/market_data/source_evidence.py`
- [X] T270 [P] Create deterministic MT5, CME, Cboe, Coinbase, OpenAI, Anthropic, outage, entitlement, conflict, DST, and stale-cache fixtures without production secrets in `tests/fixtures/market_research.py`

**Checkpoint**: The amended persistence and contracts can represent every source, schedule,
fallback, category outcome, and LLM attempt without making any source or AI result authoritative by
configuration alone.

---

## Phase 16: User Story 2 Amendment — Automated Three-Category Market Research (Priority: P1)

**Goal**: Run one manual or scheduled research job across Commodity, Forex, and Cryptocurrency,
using MT5 broker authority plus asset-specific specialist evidence, deterministic gates/ranking,
ordered fail-closed fallback, and optional run-pinned LLM explanation inside the current Markets
workspace.

**Independent Test**: From a verified MT5 fixture account, close the browser and advance a due
schedule. Exactly one parent with three category children—or one overlap skip—must persist. Each
category must preserve source semantics and independently recommend or block; MT5-unsupported,
stale, incomplete, or conflicting evidence must never rank. Changing or failing the selected LLM
must alter no deterministic gate, metric, score, rank, proposal, or active assignment.

### Tests for the User Story 2 Amendment

- [X] T271 [P] [US2] Write qualification contract tests for CME, Cboe, and Coinbase authentication, entitlements, pagination/stream recovery, rate limits, revisions, capability declarations, redaction, and normalized outputs in `tests/contract/test_specialist_market_data_adapters.py`
- [X] T272 [P] [US2] Extend native MT5 EA tests for broker-symbol authority, multi-window bars/activity, broker real-volume semantics, optional Depth of Market, unavailable-not-zero behavior, account binding, and the denied trade-call surface in `tests/safety/test_mt5_ea_bridge.py`
- [X] T273 [P] [US2] Write source-authority and quality tests for mappings, provider/venue provenance, actual/proxy semantics, unchanged capability freshness, MT5 support veto, and material-conflict quarantine in `tests/data_quality/test_market_source_authority.py`
- [X] T274 [P] [US2] Write deterministic asset-aware liquidity gate tests requiring Forex broker spread/activity proxies, Commodity venue volume/open interest and entitled depth, and Cryptocurrency venue volume/order-book depth in `tests/unit/market_research/test_asset_liquidity.py`
- [X] T275 [P] [US2] Write ordered fallback tests proving three bounded specialist attempts, then current complete MT5, then still-fresh cached external evidence, with no weakened gate, extended freshness, silent substitution, or active-assignment change in `tests/safety/test_market_source_fallback.py`
- [X] T276 [P] [US2] Write schedule tests for one-hour-to-30-day intervals, anchored local starts, IANA time zones/DST, unique due claims, overlap skips, no catch-up, lease fencing, and browser-independent execution in `tests/integration/test_market_research_scheduler.py`
- [X] T277 [P] [US2] Write coordinated-run tests for one parent, exactly three category children, independent completion/blocking, immutable policy/source pins, crash recovery, idempotent redelivery, and preserved active assignments in `tests/integration/test_coordinated_market_research.py`
- [X] T278 [P] [US2] Write LLM boundary tests for fixed provider/model allowlists, one global future-run selection, atomic run pinning, minimized prompts, strict output schema, three timed attempts, same-model explicit retry, no substitution, and deterministic-output immutability in `tests/safety/test_market_research_llm_boundary.py`
- [X] T279 [P] [US2] Write authenticated HTTP contract tests for schedule, global model configuration, coordinated start/report, category evidence, overlap status, and pinned-analysis retry operations in `tests/contract/test_market_research_automation_api.py`
- [X] T280 [P] [US2] Write the accessible in-place Markets journey for provider readiness, schedule/model controls, browser-closed execution, three category outcomes, provenance/fallback evidence, blocked states, LLM failure/retry, and separate activation confirmation in `apps/web/tests/e2e/market_research_automation.spec.ts`

### Implementation for the User Story 2 Amendment

- [ ] T281 [US2] Extend the native EA payload with bounded multi-window bars/activity, broker real volume, optional Depth of Market capability/status, source times, and explicit unavailable fields while retaining outbound-only HTTPS and no trade calls in `apps/mt5_bridge/mql5/TraderXReadOnlyBridge.mq5`
- [ ] T282 [US2] Validate and normalize the extended EA market-evidence payload without treating partial/null sections as empty or globally authoritative in `src/traderx/integrations/mt5_bridge.py`
- [ ] T283 [US2] Implement a persistent HTTP/stream transport with rate-limit handling, bounded retries, redaction, raw-response hashing, and normalized provider errors for reviewed specialist adapters in `src/traderx/market_data/providers/http.py`
- [ ] T284 [P] [US2] Implement the CME Group adapter for entitled futures metadata, trades/top-of-book, cleared volume, open interest, settlement, and optional depth with licensing/capability enforcement in `src/traderx/market_data/providers/cme_group.py`
- [ ] T285 [P] [US2] Implement the Cboe FX Spot adapter for explicitly venue-specific instruments, volume, prints, top-of-book, and entitled depth without claiming a consolidated Forex book in `src/traderx/market_data/providers/cboe_fx_spot.py`
- [ ] T286 [P] [US2] Implement the Coinbase Exchange adapter for products, trades, candles, actual venue volume, and sequence-reconciled L2/L3 order books in `src/traderx/market_data/providers/coinbase_exchange.py`
- [ ] T287 [US2] Implement owner-approved MT5-to-venue symbol mapping, contract-variant checks, entitlement verification, catalogue-revision binding, and unsupported-symbol vetoes in `src/traderx/market_data/mapping.py`
- [ ] T288 [US2] Extend ingestion to retain provider-native batches, source/capability manifests, immutable revisions, cached-success eligibility metadata, and mapping versions before canonical normalization in `src/traderx/market_data/ingestion.py`
- [ ] T289 [US2] Extend quality evaluation with capability-specific freshness, incomplete-versus-unavailable distinction, cross-source coherence checks, quarantine, and unchanged outage limits in `src/traderx/market_data/quality.py`
- [ ] T290 [US2] Replace generic depth proxies with asset-aware Forex, Commodity, and Cryptocurrency liquidity evidence and explicit unknown mandatory measures in `src/traderx/market_research/liquidity.py`
- [ ] T291 [US2] Enforce MT5 broker support before source, data, liquidity, execution, sizing, hours, gap, and prop-firm gates and preserve every reason before volatility ranking in `src/traderx/market_research/eligibility.py`
- [ ] T292 [US2] Implement specialist-primary selection and the exact specialist-to-current-MT5-to-fresh-cache fallback state machine with reason-coded blocked outcomes in `src/traderx/market_research/source_selection.py`
- [ ] T293 [US2] Rebuild category research orchestration around immutable source manifests, deterministic multi-horizon metrics, asset-aware gates, suitability versions, fallback trails, and no-activation proposals in `src/traderx/market_research/service.py`
- [ ] T294 [P] [US2] Define the minimized normalized-evidence prompt envelope and strict advisory summary/anomaly/caution/method-proposal response schema in `src/traderx/market_research/llm_schema.py`
- [ ] T295 [US2] Implement global-model validation, atomic provider/model/catalogue/prompt/schema/inference pinning, bounded same-model attempts, explicit retry, visible failure states, and deterministic-result independence in `src/traderx/market_research/llm_analysis.py`
- [ ] T296 [P] [US2] Implement the reviewed OpenAI Responses adapter with `store=false` where supported, strict structured output, no tools, allowlisted model IDs, redacted errors, usage evidence, and no automatic substitution in `src/traderx/integrations/providers/openai_responses.py`
- [ ] T297 [P] [US2] Implement the reviewed Anthropic Messages adapter with strict structured output, no tools, allowlisted model IDs, redacted errors, usage evidence, and no automatic substitution in `src/traderx/integrations/providers/anthropic_messages.py`
- [ ] T298 [US2] Implement authorized, versioned global schedule and future-runs-only model configuration commands with ETags, idempotency, deliberate reason, audit, and outbox facts in `src/traderx/market_research/configuration.py`
- [ ] T299 [US2] Implement PostgreSQL-authoritative due calculation, unique occurrence claims, anchored timezone/DST semantics, overlap skips, next-run advancement, and lease recovery in `src/traderx/market_research/scheduling.py`
- [ ] T300 [US2] Implement coordinated parent creation, exactly-three category dispatch, immutable policy/model pins, independent outcome aggregation, partial completion, and preserved assignments in `src/traderx/market_research/coordinator.py`
- [ ] T301 [US2] Implement specialist collection, source fallback, deterministic category evaluation, advisory analysis, durable progress, and idempotent checkpoint tasks in `apps/worker/traderx_worker/tasks/market_research.py`
- [ ] T302 [US2] Replace the fixed daily rotation trigger with the due-schedule scanner, coordinated parent dispatch, overlap recording, and crash-safe resumption in `apps/worker/traderx_worker/tasks/market_rotation.py`
- [ ] T303 [US2] Configure Celery Beat to wake only the database due scanner and route coordinated/category/LLM work without owning schedule truth in `apps/worker/traderx_worker/runtime/celery_app.py`
- [ ] T304 [US2] Implement schedule, global model, coordinated run/report, source evidence, and pinned-analysis retry routes with authenticated OWNER mutations and read access from `contracts/http-api.yaml` in `apps/api/traderx_api/routes/markets.py`
- [ ] T305 [US2] Define and transactionally emit schedule, occurrence, coordinated completion, category block, source fallback, model change, and LLM analysis facts from `contracts/domain-events.md` in `src/traderx/market_research/events.py`
- [ ] T306 [US2] Regenerate the typed web client for the implemented schedule, catalogue, model, coordinated-run, evidence, and retry schemas in `apps/web/src/lib/api/generated.ts`
- [ ] T307 [P] [US2] Build global model selection, anchored schedule configuration, next/last/overlap status, manual run-all, and valid permission/error states as an embedded Markets panel in `apps/web/src/features/markets/MarketResearchControls.tsx`
- [ ] T308 [US2] Replace the category-only placeholder flow with the embedded controls, one coordinated run history, three result states, and existing activation/replacement components in `apps/web/src/features/markets/MarketsWorkspace.tsx`
- [ ] T309 [P] [US2] Display asset-specific source/venue/mapping/capability semantics, observed age/policy, conflicts, fallback trail, deterministic metrics/ranks, pinned LLM status/advice, and same-model retry without conflating ranking and activation in `apps/web/src/features/markets/MarketResearchReport.tsx`
- [ ] T310 [P] [US2] Expose source coverage, mapping, entitlement, freshness, and actual/proxy/unavailable states for researched and inactive instruments in `apps/web/src/features/markets/InstrumentLibrary.tsx`

**Checkpoint**: User Story 2 meets FR-015–FR-029 and FR-095–FR-105 plus SC-004–SC-006 and
SC-019–SC-022 without creating a second UI or granting the LLM financial authority.

---

## Phase 17: User Story 9 Amendment — Reviewed Provider Operations in the Current UI (Priority: P2)

**Goal**: Let an authorized owner configure and operate the fixed market-data and LLM catalogues
from the existing Integrations/System areas with protected credentials, qualification evidence,
health, audit, and actionable failures.

**Independent Test**: From the authenticated Integrations panel, connect, test, disable, re-enable,
rotate, and remove each reviewed non-broker provider; reject arbitrary providers, URLs, or models;
never return or log a credential; and reflect provider failure immediately in source/model
eligibility while retaining historical evidence.

### Tests for the User Story 9 Amendment

- [ ] T311 [P] [US9] Write provider-catalogue and non-broker lifecycle contract tests for fixed entries, provider-specific schemas, licensing acceptance, masked responses, connect/test/enable/disable/rotate/remove, ETags, idempotency, and health in `tests/contract/test_provider_catalogue_api.py`
- [ ] T312 [P] [US9] Write security and integration tests rejecting arbitrary endpoints/models, unauthorized secret operations, stale versions, secret exposure, unqualified entitlement/mapping, and retired adapters in `tests/security/test_provider_catalogue_security.py`
- [ ] T313 [P] [US9] Write the existing-UI browser journey for CME/Cboe/Coinbase/OpenAI/Anthropic catalogue cards, credential lifecycle, licensing/retention notices, health/error recovery, and permission states in `apps/web/tests/e2e/provider_catalogue_operations.spec.ts`

### Implementation for the User Story 9 Amendment

- [ ] T314 [US9] Extend non-broker lifecycle commands with catalogue-bound configuration validation, write-only encrypted credentials, licensing/retention acknowledgement, qualification state, removal, rotation, step-up authorization, audit, and outbox writes in `src/traderx/integrations/service.py`
- [ ] T315 [US9] Implement reviewed catalogue listing and non-broker create/test/enable/disable/rotate/remove endpoints without generic URLs or secret-bearing responses in `apps/api/traderx_api/routes/integrations.py`
- [ ] T316 [P] [US9] Implement provider qualification, capability probing, entitlement checks, bounded health polling, credential-rotation verification, and redacted failure tasks in `apps/worker/traderx_worker/tasks/operations.py`
- [ ] T317 [US9] Aggregate provider capability freshness, current error, entitlement, catalogue lifecycle, and research impact into `HEALTHY`, `DEGRADED`, `FAILED`, or `DISABLED` states in `src/traderx/integrations/health.py`
- [ ] T318 [US9] Extend the existing integration cards with reviewed market-data and LLM provider-specific forms, masked credential actions, licensing/retention notices, test/enable/disable/rotate/remove controls, and accessible status guidance in `apps/web/src/features/integrations/Integrations.tsx`
- [ ] T319 [P] [US9] Display specialist source, selected-model, schedule-worker, entitlement, freshness, and affected-category health without exposing sensitive configuration in `apps/web/src/features/system/SystemControl.tsx`
- [ ] T320 [P] [US9] Route catalogue retirement, entitlement loss, stale/conflicting source, schedule overlap/failure, and unavailable LLM facts through durable user-selected notifications in `src/traderx/notifications/router.py`

**Checkpoint**: User Story 9 satisfies FR-079–FR-094 and FR-097/FR-102 for the amended providers;
routine operation remains authenticated, audited, secret-safe, and entirely inside the current UI.

---

## Phase 18: Market-Research Amendment Release Gates

**Purpose**: Reconcile contracts and prove source, scheduling, LLM, security, accessibility,
resilience, and constitutional behavior before enabling the amended feature in production.

- [ ] T321 [P] Add static guards against scraping, arbitrary provider/model registration, LLM tools or account-data prompts, deterministic-result mutation by analysis, and any MT5/live-order capability in `tests/safety/test_constitutional_negative_capabilities.py`
- [ ] T322 [P] Add SC-019–SC-022 end-to-end acceptance tests for unique scheduling, source authority, unchanged-gate fallback, exact run pinning, visible LLM failure, and no automatic activation/replacement in `tests/e2e/test_market_research_acceptance.py`
- [ ] T323 [P] Add scheduler throughput, three-category completion, bounded provider/LLM retry, API report latency, and large evidence-table scenarios to `tests/performance/test_success_criteria.py`
- [ ] T324 [P] Add keyboard, screen-reader, focus, live-region, non-colour status, responsive table, loading/empty/stale/conflict/rate-limit/permission, and recovery checks for the amended panels in `apps/web/tests/e2e/accessibility.spec.ts`
- [ ] T325 Document provider entitlement acquisition, credential rotation, symbol-mapping approval, retention/licensing review, outage/fallback response, model retirement, and scheduler recovery in `deploy/operations/market-research-runbook.md`
- [ ] T326 Reconcile runtime OpenAPI generation, typed client, provider ports, and market-research event schemas and update the authoritative status in `specs/001-traderx-core-platform/contracts/compatibility-report.md`
- [ ] T327 Execute the amended integration, three-category, fallback, schedule, LLM, restart, and browser-closed scenarios and record evidence in `specs/001-traderx-core-platform/quickstart-results.md`
- [ ] T328 Map FR-095–FR-105 and SC-019–SC-022 to code, migration, UI, audit/event, and passing test evidence while preserving the full 105/22 mapping in `specs/001-traderx-core-platform/traceability.md`
- [ ] T329 Re-run the Constitution Check for official sources, deterministic authority, human activation, UI-first operation, preserved evidence, and manual execution and record the release decision in `specs/001-traderx-core-platform/constitution-compliance.md`
- [ ] T330 Update user guidance for provider prerequisites, global model selection, recurring research, evidence/fallback interpretation, analysis retry, and human market approval in `README.md`

**Checkpoint**: The amendment is production-eligible only when every required provider is legally
usable and qualified for the deployed account, all SC-019–SC-022 evidence passes, and T245–T248
plus T321–T330 are complete.

---

## Amendment Dependencies and Execution Order

### Phase Dependencies

- **Phase 15 — Amendment Foundation**: Depends on the existing Phase 2 foundation and blocks the
  amended US2 and US9 work.
- **Phase 16 — US2 Amendment**: Depends on Phase 15. Tests T271–T280 are authored first; adapters
  T284–T286 may proceed in parallel after T283; provider and LLM adapters converge before T293,
  T295, and coordinated execution.
- **Phase 17 — US9 Amendment**: Depends on the Phase 15 catalogue/secret model. It may begin in
  parallel with Phase 16 using qualification fixtures, then integrates with implemented provider
  adapters and market-research health.
- **Phase 18 — Release Gates**: Depends on the desired Phase 16 and Phase 17 scope and joins the
  original release tasks T245–T248 and convergence task T260.

### Amendment User Story Dependency Graph

```text
Existing Foundation -> Phase 15 Amendment Foundation
Phase 15 -> US2 Amendment
Phase 15 -> US9 Amendment
US2 Amendment + US9 Amendment -> Phase 18 Release Gates
US2 deterministic report -> existing human activation/replacement commands
US9 health -> US2 provider/model eligibility, never deterministic financial authority
```

### Parallel Execution Examples

#### User Story 2 Amendment

```text
Parallel tests: T271, T272, T273, T274, T275, T276, T277, T278, T279, T280
Parallel specialist adapters after T283: T284, T285, T286
Parallel LLM adapters after T294: T296, T297
Parallel UI components after T304 and T306: T307, T309, T310
```

#### User Story 9 Amendment

```text
Parallel tests: T311, T312, T313
Parallel worker/UI health surfaces after T314 and T315: T316, T319, T320
```

## Amendment Implementation Strategy

### MVP First: Deterministic Scheduled Research

1. Complete Phase 15.
2. Write T271–T280 and confirm each fails for the intended missing behavior.
3. Complete the MT5 evidence, source normalization, asset-aware gates, fallback, scheduler,
   coordinator, API, and current-UI tasks needed for deterministic three-category reports.
4. Validate manual and scheduled runs without enabling an LLM; a healthy LLM is not a prerequisite
   for deterministic results.
5. Add reviewed LLM analysis and explicit same-model retry, then prove zero deterministic drift.

### Incremental Delivery

1. Deliver MT5 broker authority plus synthetic/licensed specialist fixtures and blocked unknowns.
2. Qualify one specialist adapter per category without relaxing any category gate.
3. Deliver database scheduling and coordinated three-category reporting in the current Markets UI.
4. Add the global reviewed model selector and non-authoritative analysis.
5. Deliver complete provider lifecycle/health in the current Integrations/System UI.
6. Enable production providers only after entitlement, licensing, symbol mapping, security, and
   release evidence pass.

### Amendment Notes

- All new task descriptions name one exact repository-relative file path; task IDs remain
  sequential after the preserved implementation history.
- Tests are mandatory and precede implementation because the amendment affects financial evidence,
  fail-closed eligibility, external secrets, scheduling concurrency, and AI boundaries.
- Provider and model catalogue values are reviewed code/data, not user-entered arbitrary endpoints.
- The LLM may fail completely without blocking publication of a valid deterministic research report.
- No task may activate or replace a market, weaken a gate/freshness limit, or add a live-order
  operation automatically.
