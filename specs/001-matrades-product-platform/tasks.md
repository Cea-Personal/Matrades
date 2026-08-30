# Tasks: Matrades Product Platform — Autonomous Execution

**Input**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md), and [Constitution 3.0.0](../../.specify/memory/constitution.md)

**Scope**: This forward backlog replaces the legacy HIL/manual-entry workflow with bounded, per-account autonomous execution. It preserves historical HIL/proposal/approval records as read-only `LEGACY_UNTYPED` evidence but creates no new HIL state, approval queue, or manual-entry transition. Every broker write is produced only by deterministic authorization and an idempotent execution command; agents, charts, and Knowledge Assistant requests cannot bypass that boundary.

**Tests**: Required. The specification, Constitution, contracts, and quickstart require unit, property, contract, replay, security, integration, browser, failure-injection, and acceptance evidence. Write each listed test before its implementation task and verify it fails for the intended missing behavior.

**Format**: `[P]` marks work that can proceed in parallel after its stated prerequisites. `[USn]` maps a task to the user story in `spec.md`.

## Phase 1: Setup and Contract Baseline

**Purpose**: Make the autonomous-execution contract, deterministic fixtures, and migration workflow reproducible before domain changes.

- [X] T001 Reconcile the generated OpenAPI clients with the autonomous contract and fail CI on stale output in `scripts/generate_contracts.py`
- [X] T002 Add autonomous contract generation, schema validation, and selected quickstart targets in `Makefile`
- [X] T003 [P] Add account, risk, authorization, command, fill, and reconciliation fixtures in `tests/fixtures/autonomous_execution.py`
- [X] T004 [P] Add 12-lane research, provider-source-cut, futures-roll, corporate-action, and CFD-financing fixtures in `tests/fixtures/autonomous_research.py`
- [X] T005 [P] Add MT5 bridge/EA command, timeout, duplicate, partial-fill, and restart fixtures in `tests/fixtures/mt5_bridge.py`
- [X] T006 [P] Add journal, chart, knowledge-citation, analytics-population, and notification fixtures in `tests/fixtures/live_trade.py`
- [X] T007 Add PostgreSQL, Redis, agent-worker, bridge-test, and optional LiteLLM service profiles for the new suites in `infra/compose/compose.yaml`
- [X] T008 [P] Add autonomous execution, bridge replay, chart-read-only, and SC-001–SC-024 jobs in `.github/workflows/ci.yml`

**Checkpoint**: A clean checkout can generate contracts, load deterministic fixtures, and run the autonomous test targets without a live provider or broker.

## Phase 2: Foundational Authority, Persistence, and Compatibility

**Purpose**: Establish the persistent authority order and migration seam that every story depends on.

**Critical**: No user-story work may enable a broker write before this phase completes.

- [X] T009 Define autonomous execution actions, command states, evidence classes, and safe-status enums in `packages/shared/domain_types.py`
- [X] T010 Add immutable execution-permission, kill-switch, Trade Plan, authorization, command, attempt, broker-order/fill/position, and reconciliation entities in `modules/trading/models.py`
- [X] T011 Extend account, policy, risk-reservation, journal, and performance persistence relationships for autonomous execution in `modules/accounts/models.py`, `modules/risk/models.py`, `modules/journal/models.py`, and `modules/performance/models.py`
- [X] T012 Create an expand/dual-read/new-write migration that preserves legacy HIL/proposal/approval records as non-actionable evidence in `infra/migrations/versions/0012_autonomous_execution.py`
- [X] T013 Implement legacy read adapters and reject all new HIL/manual-entry writes in `modules/trading/legacy_compatibility.py`
- [X] T014 Add transactional outbox, optimistic-version, idempotency, correlation, and causation helpers for command-producing aggregates in `packages/shared/outbox.py` and `packages/shared/idempotency.py`
- [X] T015 Implement execution authority-order guards and forbidden direct broker-write dependency checks in `modules/trading/authority.py` and `tests/security/test_execution_authority_boundaries.py`
- [X] T016 Extend event schemas for permissions, kill switches, Trade Plans, commands, broker facts, journal indexing, charts, analytics, and notifications in `packages/contracts/events.py`
- [X] T017 Replace legacy HIL/manual OpenAPI paths and generate autonomous API models in `specs/001-matrades-product-platform/contracts/openapi.yaml` and `packages/contracts/generated/openapi.py`
- [X] T018 [P] Generate the matching TypeScript API models and stale-contract test in `packages/contracts/generated/openapi.ts` and `apps/web/src/contracts/openapi.test.ts`
- [X] T019 Add database constraints preventing an execution command without account scope, action, idempotency identity, and immutable evidence references in `packages/shared/persistence.py`
- [X] T020 Add authority-order, migration, event-envelope, and contract-reference tests in `tests/contract/test_autonomous_foundation.py`
- [X] T021 Add migration forward/rollback, legacy-read, and no-new-HIL-write integration tests in `tests/integration/test_autonomous_execution_migration.py`
- [X] T022 Add structured error mapping for stale authority, disabled action, active kill switch, conflict, and unknown-outcome states in `apps/api/app/errors.py`

**Checkpoint**: PostgreSQL owns the execution state machine and no API, agent, UI, or adapter can create a new HIL/manual-entry workflow or bypass deterministic authority checks.

## Phase 3: User Story 1 — Execute a Safe Automated Trade (Priority: P1) 🎯 MVP

**Goal**: Build a complete, risk-checked Trade Plan that becomes one broker order only when every fresh hard check and the account’s `NEW_ENTRY` permission pass.

**Independent Test**: With one account, validated strategy, fresh data, and an enabled entry permission, prove PASS creates one authorized command and one recording-adapter request; prove REDUCE SIZE recomputes safely; prove HARD BLOCK, stale data, or a disabled permission reaches no adapter write.

### Tests for User Story 1

- [X] T023 [P] [US1] Add contract tests for Trade Plan, execution authorization, and read-only command endpoints in `tests/contract/test_trade_plan_execution_api.py`
- [X] T024 [P] [US1] Add property tests for strictest-limit monotonicity, current-equity requirements, reserved risk, and safe size rounding in `tests/property/test_autonomous_risk_invariants.py`
- [X] T025 [P] [US1] Add concurrency tests proving candidate reservations cannot oversubscribe capacity in `tests/integration/test_trade_plan_reservation_concurrency.py`
- [X] T026 [P] [US1] Add end-to-end PASS, REDUCE_SIZE, HARD_BLOCK, stale snapshot, and disabled-permission coverage in `tests/e2e/test_safe_automated_trade.py`

### Implementation for User Story 1

- [X] T027 [P] [US1] Extend account snapshot capture to create one consistent broker cut with equity, drawdown, positions, orders, and freshness in `modules/accounts/snapshots.py`
- [X] T028 [P] [US1] Implement type-aware spot, CFD, and futures worst-case valuation, currency conversion, and safe rounding in `modules/risk/financial_math.py` and `modules/risk/position_sizing.py`
- [X] T029 [P] [US1] Implement Stop-Loss reserved risk, shared-underlying exposure, correlation, and dynamic additional-trade capacity in `modules/risk/reserved_risk.py`, `modules/risk/exposure.py`, and `modules/risk/trade_capacity.py`
- [X] T030 [US1] Enforce current snapshot, policy, guardrail, freshness, and hard-block authority ordering in `modules/risk/authority.py` and `modules/risk/engine.py`
- [X] T031 [US1] Construct immutable Trade Plans with FR-032/FR-084 evidence, exact instrument references, and candidate reservations in `modules/trading/construction.py`
- [X] T032 [US1] Implement deterministic strategy selection, setup detection, critic gating, and Trade Plan state transitions in `modules/trading/setup_detector.py`, `modules/trading/critic.py`, and `modules/trading/trade_plans.py`
- [X] T033 [US1] Implement short-lived entry authorization that rereads permission version, kill-switch epochs, risk reservation, broker state, and plan expiry in `modules/trading/authorization.py`
- [X] T034 [US1] Implement command creation, transactional outbox insertion, and recording-adapter dispatch seam without exposing arbitrary command submission in `modules/trading/execution.py`
- [X] T035 [US1] Expose Trade Plan, risk snapshot, and read-only execution-command API queries in `apps/api/app/routes/trade_plans.py` and `apps/api/app/main.py`
- [X] T036 [US1] Replace approval/manual-entry controls with Trade Plan state, restrictions, and risk evidence in `apps/web/src/features/trading/TradeProposalPanel.tsx`
- [X] T037 [US1] Display complete current-equity capacity, limiting sources, reduced size, and hard-block explanations in `apps/web/src/features/risk/RiskSnapshot.tsx`
- [X] T038 [US1] Add regression tests rejecting direct agent, API, or UI broker dispatch without authorization in `tests/security/test_no_execution_bypass.py`
- [X] T039 [US1] Add 5-second candidate-evaluation SLO and immutable evidence replay coverage in `tests/integration/test_trade_plan_slos.py` and `tests/replay/test_trade_plan_reproducibility.py`

**Checkpoint**: A safe, visible Trade Plan can authorize one entry command; all unsafe states are explicit and produce zero broker writes.

## Phase 4: User Story 2 — Research Markets for the Session (Priority: P1)

**Goal**: Run daily autonomous research across all enabled `(asset_class, instrument_type)` lanes and advance only same-lane eligible candidates into analysis.

**Independent Test**: Run a full configured 12-lane matrix and verify exactly one terminal result per lane, autonomous progression of READY candidates, deterministic same-lane fallback, and a truthful safe outcome for unavailable data.

### Tests for User Story 2

- [X] T040 [P] [US2] Add 12-lane OpenAPI and event-contract coverage for terminal states and selection lineage in `tests/contract/test_autonomous_research_contract.py`
- [X] T041 [P] [US2] Add replay coverage for source cuts, ranking, invalidation, and same-lane fallback in `tests/replay/test_autonomous_daily_research.py`
- [X] T042 [P] [US2] Add provider capability, staleness, quota, and no-cross-wrapper fallback tests in `tests/failure/test_research_lane_failures.py`
- [X] T043 [P] [US2] Add browser coverage for the 12-lane matrix, research schedule, and safe-status explanations in `tests/e2e/test_autonomous_market_selection.py`

### Implementation for User Story 2

- [X] T044 [P] [US2] Persist account research-matrix versions, lane schedules, provider bindings, source cuts, ranked candidates, and selection lineage in `modules/research/models.py` and `modules/analysis/models.py`
- [X] T045 [P] [US2] Implement capability-routed provider resolution and same-lane fallback selection in `modules/connections/resolution.py` and `modules/research/matrix.py`
- [X] T046 [P] [US2] Normalize Twelve Data, Coinbase, CoinGecko, broker, futures, macro, positioning, calendar, and news observations with provenance/freshness in `adapters/market_data/twelve_data/client.py`, `adapters/market_data/coinbase/client.py`, `adapters/market_data/coingecko/client.py`, `adapters/market_data/futures_reference.py`, `adapters/macro/providers.py`, `adapters/calendar/provider.py`, and `adapters/news/provider.py`
- [X] T047 [US2] Implement scheduled source-cut reuse, quota-aware batching, and immutable timestamped research archives in `modules/research/scheduling.py`, `modules/research/workflow.py`, and `modules/research/artifacts.py`
- [X] T048 [US2] Implement four asset-class specialist lane rankings and bounded orchestrator aggregation for all 12 lanes in `modules/analysis/research_roles.py` and `modules/analysis/daily_research.py`
- [X] T049 [US2] Implement selection invalidation and deterministic next-candidate progression without approval states in `modules/analysis/daily_research.py`
- [X] T050 [US2] Expose matrix configuration, schedules, research runs, and immutable market selections in `apps/api/app/routes/research_matrix.py` and `apps/api/app/routes/research.py`
- [X] T051 [US2] Replace pair-entry and approval UX with schedule-aware autonomous lane results in `apps/web/src/features/research/MarketSelection.tsx` and `apps/web/src/app/research/page.tsx`
- [X] T052 [US2] Add research archive-folder browsing and checksummed manifest links in `apps/api/app/routes/extras.py` and `apps/web/src/features/extras/Extras.tsx`
- [X] T053 [US2] Add 10-minute matrix SLO, provider source-cut sharing, and typed listing/dated-contract replay tests in `tests/integration/test_autonomous_research_slos.py`

**Checkpoint**: Every enabled lane ends in one auditable candidate or a truthful safe terminal state; no research result grants trade capacity or requires a routine human selection approval.

## Phase 5: User Story 3 — Execute and Manage a Trade Automatically (Priority: P1)

**Goal**: Dispatch bounded broker commands through the MT5 bridge, reconcile actual state before any retry, manage positions under action-specific permissions, and present a read-only live workspace.

**Independent Test**: In a demo bridge environment, execute entry, reconciliation, protection change, partial close, and full exit once each; inject timeout/restart/duplicate/ambiguous outcomes; activate the kill switch; confirm chart controls cannot create commands.

### Tests for User Story 3

- [X] T054 [P] [US3] Add BrokerAdapter capability, signed-command, and response-schema contract tests in `tests/contract/test_execution_broker_adapter.py`
- [X] T055 [P] [US3] Add command idempotency, stale epoch, expiry, permission, and expected-version security tests in `tests/security/test_execution_command_security.py`
- [X] T056 [P] [US3] Add bridge/EA restart, lost-response, partial-fill, cancel-fill-race, and reconciliation-before-retry tests in `tests/integration/test_mt5_execution_bridge.py`
- [X] T057 [P] [US3] Add autonomous lifecycle, kill-switch, and unknown/ambiguous outcome browser tests in `tests/e2e/test_autonomous_trade_lifecycle.py`
- [X] T058 [P] [US3] Add active Trade Plan, read-only chart overlays, and no-command chart interaction tests in `tests/e2e/test_live_trade_workspace.py`

### Implementation for User Story 3

- [X] T059 [P] [US3] Implement account action-permission versions and step-up-protected activation in `modules/trading/permissions.py` and `apps/api/app/routes/accounts.py`
- [X] T060 [P] [US3] Implement durable platform/account kill switches, monotonic safety epochs, and dispatch fencing in `modules/security/platform.py` and `modules/trading/kill_switches.py`
- [X] T061 [US3] Implement the durable execution-command state machine, attempts, leases, and outbox consumer in `modules/trading/execution.py` and `apps/worker/app/tasks/execution.py`
- [X] T062 [US3] Extend the broker port for bounded submit, cancel, protection, partial-close, full-exit, orders, fills, positions, and history calls in `modules/trading/broker_port.py`
- [X] T063 [US3] Implement command authorization verification, signed envelopes, and account/capability checks in `adapters/broker/mt5_bridge/client.py`
- [X] T064 [US3] Implement the durable bridge queue, transactional lease ledger, HMAC/mTLS verification, and health endpoint in `bridges/mt5/app.py`, `bridges/mt5/reader.py`, and `bridges/mt5/health.py`
- [X] T065 [US3] Update the EA to poll outbound `WebRequest`, persist command identity, validate safety data, call `MqlTradeRequest`, and post receipts/events in `bridges/mt5/MatradesMT5BridgeEA.mq5`
- [X] T066 [US3] Implement order/fill/position normalization, external-activity detection, and exact typed reconciliation in `modules/trading/reconciliation.py` and `modules/trading/broker_models.py`
- [X] T067 [US3] Implement unknown-outcome and ambiguous-match handling that reconciles before same-identity retry in `modules/trading/reconciliation.py` and `modules/trading/reconciliation_decisions.py`
- [X] T068 [US3] Implement autonomous monitoring actions with fresh policy/risk/permission/kill revalidation in `modules/trading/monitor.py` and `modules/trading/monitor_agent.py`
- [X] T069 [US3] Remove legacy HIL-2/HIL-3/manual-entry dispatch paths and leave read-only legacy views in `modules/trading/hil2.py`, `modules/trading/hil3.py`, `modules/trading/manual_entry.py`, and `modules/trading/proposals.py`
- [X] T070 [US3] Expose execution permissions, account/platform kill switches, operations, broker order/position, and reconciliation evidence in `apps/api/app/routes/operations.py` and `apps/api/app/routes/trade_management.py`
- [X] T071 [US3] Replace approval inbox controls with account-grouped automation operations and kill-switch state in `apps/web/src/features/approvals/ApprovalInbox.tsx` and `apps/web/src/app/operations/page.tsx`
- [X] T072 [US3] Display active Trade Plan, commands, attempts, broker facts, reconciliation certainty, and action restrictions in `apps/web/src/features/trading/TradeManagement.tsx`
- [X] T073 [US3] Implement a read-only chart data/overlay service with freshness/mapping degradation in `modules/trading/charts.py` and `apps/api/app/routes/trade_management.py`
- [X] T074 [US3] Build the active-trade chart with plan, fill, protection, management, and journal overlays but no command mutation path in `apps/web/src/features/trading/ActiveTradeChart.tsx`
- [X] T075 [US3] Implement confirmed-entry notification intent, fill-version dedupe, and in-product/Telegram/Pushover delivery in `modules/notifications/service.py`, `modules/notifications/providers.py`, and `adapters/notifications/channels.py`

**Checkpoint**: Commands are effectively-once economic intents, unknown broker outcomes reconcile before retry, action/kill controls fence writes, and the active-trade view remains observably read-only.

## Phase 6: User Story 4 — Create and Validate a Strategy (Priority: P2)

**Goal**: Support AI-generated and AI-assisted strategies with human canonicalization, origin-neutral validation, and promotion only after reproducible evidence.

**Independent Test**: Generate an autonomous hypothesis and an assisted draft, approve one canonical rule set, detect a duplicate, run the same validation/paper lifecycle, and prove neither can become live early.

### Tests for User Story 4

- [X] T076 [P] [US4] Add strategy-origin, canonicalization, and duplicate/variant contract tests in `tests/contract/test_strategy_autonomous_contract.py`
- [X] T077 [P] [US4] Add deterministic evidence-pack, no-look-ahead, and unseen-holdout replay tests in `tests/replay/test_strategy_evidence_pack.py`
- [X] T078 [P] [US4] Add origin-neutral backtest/paper/live parity and promotion-block tests in `tests/integration/test_strategy_autonomous_validation.py`
- [X] T079 [P] [US4] Add browser coverage for strategy family, suggestion review, comparison, validation, and promotion gates in `tests/e2e/test_strategy_origins.py`

### Implementation for User Story 4

- [X] T080 [P] [US4] Extend strategy drafts, canonical rule revisions, origins, family taxonomy, and immutable provenance in `modules/strategies/models.py`, `modules/strategies/drafts.py`, and `modules/strategies/provenance.py`
- [X] T081 [US4] Implement Strategy Researcher evidence-pack partitioning, cited hypothesis generation, and deterministic screening in `modules/strategies/ai_workflow.py` and `modules/strategies/screening.py`
- [X] T082 [US4] Implement Strategy Assistant family-aware step-by-step suggestions and human acceptance into immutable rule revisions in `modules/strategies/assistant.py` and `modules/strategies/suggestions.py`
- [X] T083 [US4] Implement canonical fingerprints, structural/semantic/behavioral similarity, and reuse/version/variant decisions in `modules/strategies/fingerprints.py`, `modules/strategies/similarity.py`, and `modules/strategies/identity.py`
- [X] T084 [US4] Pin typed listing/contract/specification, costs, financing, corporate actions, and rolls through compiler, backtest, validation, stress, paper, and promotion in `modules/strategies/compiler.py`, `modules/backtesting/engine.py`, `modules/backtesting/validation.py`, `modules/backtesting/stress.py`, `modules/backtesting/paper.py`, and `modules/backtesting/promotion.py`
- [X] T085 [US4] Expose draft, assistance, similarity, validation, and promotion APIs without a live-activation bypass in `apps/api/app/routes/strategies.py`
- [X] T086 [US4] Implement AI-generated/AI-assisted Strategy Lab flows and validation evidence views in `apps/web/src/features/strategies/StrategyBuilder.tsx`, `apps/web/src/features/strategies/SimilarityReview.tsx`, and `apps/web/src/features/strategies/ValidationResults.tsx`
- [X] T087 [US4] Add strategy lifecycle architecture tests rejecting arbitrary generated-code activation and active-version mutation in `tests/security/test_strategy_activation_boundaries.py`

**Checkpoint**: Strategy origin changes authorship, not quality gates; only a human-canonicalized, validated, paper-tested strategy can become eligible for autonomous execution.

## Phase 7: User Story 5 — Configure Accounts, Rules, and Security (Priority: P2)

**Goal**: Give users secure UI-managed accounts, rules, credentials, provider/broker connections, and notification configuration with step-up protection and masked secrets.

**Independent Test**: Complete signup/MFA, create a prop account and strict guardrail, configure and test connections, set execution permissions, then verify sensitive changes require inline step-up and that no secret is returned.

### Tests for User Story 5

- [X] T088 [P] [US5] Add signup, email, MFA, session, recovery-code, and step-up API tests in `tests/integration/test_authentication_api.py`
- [X] T089 [P] [US5] Add credential masking, inline destructive-action MFA, authorization, and audit tests in `tests/security/test_configuration_security.py`
- [X] T090 [P] [US5] Add prop-rule/guardrail/effective-limit and execution-permission configuration tests in `tests/integration/test_account_configuration.py`
- [X] T091 [P] [US5] Add provider, MT5 bridge, Telegram, Pushover, and LiteLLM connection-test contract coverage in `tests/contract/test_connection_profiles.py`
- [X] T092 [P] [US5] Add configuration and MFA-dialog browser journeys in `tests/e2e/test_secure_configuration.py`

### Implementation for User Story 5

- [X] T093 [P] [US5] Implement email verification, TOTP enrollment/challenge, recovery-code hashing, session rotation, and action-scoped step-up grants in `modules/identity/service.py`, `modules/identity/step_up.py`, and `apps/api/app/routes/auth.py`
- [X] T094 [P] [US5] Implement encrypted credential versions, masking, redaction, replacement, and bounded connection testing in `modules/credentials/vault.py`, `modules/credentials/redaction.py`, and `modules/connections/testing.py`
- [X] T095 [US5] Implement personal/prop account setup, versioned prop rules, guardrails, strictest-effective limits, and account activation checks in `modules/accounts/service.py`, `modules/prop_firms/service.py`, and `modules/policy/effective_limits.py`
- [X] T096 [US5] Implement named provider, bridge, gateway, and notification connection profiles with health/freshness history in `modules/connections/models.py`, `modules/connections/service.py`, and `modules/observability/health.py`
- [X] T097 [US5] Expose secure account, rules, credential, connection, permission, and notification configuration routes in `apps/api/app/routes/configuration.py` and `apps/api/app/routes/auth.py`
- [X] T098 [US5] Implement configuration screens for accounts/rules, connections, MT5, and notification channels in `apps/web/src/features/configuration/AccountRules.tsx`, `apps/web/src/features/configuration/Connections.tsx`, `apps/web/src/features/connections/MT5Connection.tsx`, and `apps/web/src/features/notifications/NotificationCenter.tsx`
- [X] T099 [US5] Implement the context-local step-up form that resumes credential, connection, account, or contributor deletion after MFA in `apps/web/src/components/MfaDeleteDialog.tsx` and `apps/web/src/lib/api.ts`
- [X] T100 [US5] Remove the legacy standalone sensitive-action setup panel and retain only audited inline step-up flows in `apps/web/src/app/configuration/page.tsx`
- [X] T101 [US5] Add sensitive configuration audit projections and masked export tests in `modules/observability/audit.py` and `tests/security/test_credential_vault.py`

**Checkpoint**: Users can configure the platform without source edits while security, secrets, permissions, and strictest rules remain authoritative and auditable.

## Phase 8: User Story 6 — Configure Agents Without Changing Their Authority (Priority: P2)

**Goal**: Run all required roles on Codex App Server by default, allow explicitly selected LiteLLM, and preserve independent prompt inheritance and immutable tool permissions.

**Independent Test**: Verify all 17 roles resolve to Codex by default; opt one role into LiteLLM; exercise an in-runtime fallback; test an agent; and prove permissions do not change.

### Tests for User Story 6

- [X] T102 [P] [US6] Add 17-role registry, protected-identity, and tool-permission contract tests in `tests/contract/test_agent_registry.py`
- [X] T103 [P] [US6] Add independent system/user prompt resolution and same-runtime fallback property tests in `tests/property/test_prompt_resolution.py`
- [X] T104 [P] [US6] Add Codex default, explicit LiteLLM opt-in, process recovery, and no-cross-runtime-fallback integration tests in `tests/integration/test_agent_runtime.py`
- [X] T105 [P] [US6] Add agent configuration, test-agent, runtime-health, and audit browser coverage in `tests/e2e/test_agent_configuration.py`

### Implementation for User Story 6

- [X] T106 [P] [US6] Seed and protect the 17 logical agent identities, including `stocks_research` and `knowledge_assistant`, in `modules/agents/registry.py`
- [X] T107 [P] [US6] Implement runtime-bound models/profiles/fallback validation and independent prompt selection in `modules/agents/model_profiles.py` and `modules/agents/prompts.py`
- [X] T108 [US6] Implement supervised Codex App Server worker invocation, health, bounded retries, and execution audit in `adapters/agent_runtime/codex_app_server/client.py`, `modules/agents/runtime.py`, and `modules/agents/execution_audit.py`
- [X] T109 [US6] Implement explicit LiteLLM gateway model synchronization and opt-in-only runtime routing in `adapters/agent_runtime/litellm/client.py` and `modules/agents/runtime_context.py`
- [X] T110 [US6] Enforce immutable tool-permission sets and forbid broker, permission, kill-switch, canonical-strategy, and command mutation tools in `modules/agents/permissions.py` and `tests/security/test_agent_permissions.py`
- [X] T111 [US6] Expose agent catalog, configuration versions, prompt resolution, test-agent, and runtime-health APIs in `apps/api/app/routes/agents.py`
- [X] T112 [US6] Implement Codex/LiteLLM configuration, prompt, profile, fallback, and test views in `apps/web/src/features/agents/AgentConfiguration.tsx`, `apps/web/src/features/agents/PromptConfiguration.tsx`, and `apps/web/src/features/agents/ModelProfiles.tsx`
- [X] T113 [US6] Add runtime/agent status, configured-versus-actual model, and failure-reason projections in `apps/web/src/features/health/HealthDashboard.tsx`
- [X] T114 [US6] Add architecture tests proving agents can propose structured work but cannot create authorizations, commands, permissions, or kill-switch changes in `tests/security/test_agent_execution_boundary.py`

**Checkpoint**: Agent customization is visible and provider-independent, but does not alter the authority order or create an alternative execution path.

## Phase 9: User Story 7 — Retrieve Context Without Replacing Facts (Priority: P3)

**Goal**: Provide scoped document/video/journal knowledge and a citation-grounded read-only Knowledge Assistant while keeping structured trading data authoritative.

**Independent Test**: Ingest authorized documents and a video transcript, retrieve one journal-backed answer with citations, request a trade action, and prove no Trade Plan or command exists.

### Tests for User Story 7

- [X] T115 [P] [US7] Add knowledge source lifecycle, document/transcript provenance, and search API tests in `tests/contract/test_knowledge_api.py`
- [X] T116 [P] [US7] Add owner/account semantic isolation, prompt-injection, and trading-refusal security tests in `tests/security/test_knowledge_isolation.py`
- [X] T117 [P] [US7] Add ingestion/index outage and structured-safety independence tests in `tests/failure/test_knowledge_outage.py`
- [X] T118 [P] [US7] Add Knowledge Assistant citation, insufficiency, active-trade warning, and refusal browser coverage in `tests/e2e/test_knowledge_assistant.py`

### Implementation for User Story 7

- [X] T119 [P] [US7] Implement knowledge source/document/segment/generation models and owner/account authorization filters in `modules/knowledge/models.py` and `modules/knowledge/authority.py`
- [X] T120 [P] [US7] Implement document, transcript, SerpApi, and deduplicated YouTube-transcript ingestion with protected provenance in `modules/knowledge/ingestion.py` and `modules/knowledge/youtube.py`
- [X] T121 [US7] Implement transactional journal-index work items, generation-safe embedding, retrieval audit, and degraded coverage state in `modules/knowledge/search.py` and `modules/knowledge/ports.py`
- [X] T122 [US7] Implement the read-only Knowledge Assistant with claim-level citations, inference/insufficiency labels, active-trade warning, and command refusal in `modules/knowledge/assistant.py`
- [X] T123 [US7] Expose source lifecycle, ingestion, search, and answer APIs in `apps/api/app/routes/knowledge.py`
- [X] T124 [US7] Implement source, transcript, ingestion-health, citation, and refusal UI flows in `apps/web/src/features/knowledge/KnowledgeSources.tsx` and `apps/web/src/app/knowledge/page.tsx`
- [X] T125 [US7] Add architecture tests proving risk, policy, execution, and current broker facts never read semantic answers as authority in `tests/security/test_knowledge_authority_boundary.py`

**Checkpoint**: Context is useful and cited, but unavailable or adversarial knowledge cannot alter deterministic trading, current facts, or broker behavior.

## Phase 10: User Story 8 — Review Decisions and Performance (Priority: P3)

**Goal**: Make the automated lifecycle explainable through immutable live journals, operations, evidence-separated analytics, strategy health, and delivery status.

**Independent Test**: Complete one simulated trade lifecycle, view its live journal and terminal summary, query operations, compare LIVE/PAPER/BACKTEST metrics without mixing them, and drill into the resulting edge calculation.

### Tests for User Story 8

- [X] T126 [P] [US8] Add journal reconstruction, immutable observation, terminal-summary, and index-outbox contract tests in `tests/contract/test_live_journal_contract.py`
- [X] T127 [P] [US8] Add evidence-class separation, deterministic metrics, edge, and drill-down property tests in `tests/property/test_performance_metrics.py`
- [X] T128 [P] [US8] Add operations grouping, journal-before-index, notification delivery, and strategy-health integration tests in `tests/integration/test_operations_review.py`
- [X] T129 [P] [US8] Add journal, operations, performance, and notification browser coverage in `tests/e2e/test_review_and_performance.py`

### Implementation for User Story 8

- [X] T130 [US8] Implement immutable structured journal events, evidence-linked Journal-agent observations, and terminal post-trade summaries in `modules/journal/service.py` and `modules/journal/models.py`
- [X] T131 [US8] Implement journal-to-knowledge outbox dispatch, indexing status, and post-trade summary indexing in `modules/journal/indexing.py` and `modules/knowledge/ingestion.py`
- [X] T132 [US8] Implement `BACKTEST`, `PAPER`, and `LIVE` performance observations, deterministic metric sets, after-cost edge, and drill-down references in `modules/performance/models.py` and `modules/performance/metrics.py`
- [X] T133 [US8] Implement strategy-health evaluation that creates research/suspension work without mutating active rules in `modules/performance/strategy_health.py`
- [X] T134 [US8] Implement account-grouped operations projections, urgency, execution/reconciliation state, and durable event streaming in `modules/trading/active_trades.py`, `modules/trading/events.py`, and `apps/api/app/routes/events.py`
- [X] T135 [US8] Expose Trade Journal, chart context/events, performance comparison, notification timeline, and operations APIs in `apps/api/app/routes/trade_management.py` and `apps/api/app/routes/operations.py`
- [X] T136 [US8] Implement journal timeline and active-trade evidence navigation in `apps/web/src/features/journal/JournalTimeline.tsx`
- [X] T137 [US8] Implement LIVE-default evidence-separated analytics, edge drill-down, and delivery status views in `apps/web/src/features/performance/PerformanceDashboard.tsx` and `apps/web/src/features/notifications/NotificationCenter.tsx`

**Checkpoint**: Users can reconstruct the automation lifecycle and assess performance honestly without blending simulations with live outcomes or mutating strategy rules through analytics.

## Phase 11: Polish, Safety Evidence, and Release

**Purpose**: Complete cross-cutting quality, recovery, observability, documentation, and release evidence after the selected stories are integrated.

- [X] T138 [P] Validate OpenAPI, adapter, agent, and event contracts against generated clients in `tests/contract/test_openapi_autonomous_consistency.py`
- [X] T139 [P] Add duplicate/out-of-order event, command, fill, journal-index, and notification replay tests in `tests/contract/test_autonomous_event_idempotency.py`
- [X] T140 [P] Add load/SLO tests for 12-lane research, 5-second plan evaluation, chart updates, and journal indexing in `tests/integration/test_autonomous_platform_slos.py`
- [X] T141 [P] Add failure-injection tests for agent outage, provider outage, bridge loss, stale data, kill race, unknown outcome, and index failure in `tests/failure/test_autonomous_safe_failure_matrix.py`
- [X] T142 [P] Add tenant isolation, MFA/step-up, redaction, chart-read-only, no-agent-broker-write, and execution-fencing release tests in `tests/security/test_autonomous_platform_threats.py`
- [X] T143 Add metrics, traces, structured audit events, and dashboards for commands, reconciliation, permissions, kill switches, journal lag, and notifications in `infra/observability/dashboards/matrades.json` and `modules/observability/audit.py`
- [X] T144 Update MT5 Windows, macOS/Wine, bridge queue, EA WebRequest, HMAC, and reconciliation troubleshooting guidance in `bridges/mt5/README.md`
- [X] T145 Update backup, restore, migration, kill-switch, provider quota, and unknown-outcome runbooks in `infra/deployment/restore-runbook.md`
- [X] T146 Execute every quickstart scenario and record SC-001 through SC-024 machine-readable evidence in `tests/acceptance/success_criteria.md`
- [X] T147 Run Python type/lint/test suites, generated-contract checks, web tests, and browser E2E from `Makefile`

## Dependencies and Execution Order

### Phase Dependencies

- Phase 1 has no prerequisite.
- Phase 2 depends on Phase 1 and blocks every user-story phase.
- US1 and US2 can begin after Phase 2; both are required before autonomous live-entry integration.
- US3 depends on US1 Trade Plan/authorization and US2 typed candidate/listing evidence.
- US4, US5, and US6 can begin after Phase 2; US1/US3 consume their validated strategies, configuration, and agent runtimes respectively.
- US7 can begin after Phase 2 but must not block deterministic risk or execution.
- US8 depends on durable outputs from US1–US3 and integrates US4–US7 data where available.
- Phase 11 follows all selected user stories and is mandatory before a live-connected release.

### User Story Dependency Graph

```text
Setup → Foundation
Foundation → US1 Safe Trade Plan ───────────────┐
Foundation → US2 Autonomous 12-Lane Research ──┼→ US3 Broker Execution / Monitoring → US8 Review
Foundation → US4 Strategy Validation ──────────┤
Foundation → US5 Secure Configuration ─────────┤
Foundation → US6 Agent Runtime ────────────────┤
Foundation → US7 Bounded Knowledge ────────────┘
```

## Parallel Execution Examples

### User Story 1

Run T023–T026 in parallel. After the Phase 2 entities exist, T027–T029 can proceed in parallel, then integrate through T030–T037.

### User Story 2

Run T040–T043 in parallel. T044–T046 are independent persistence/provider tasks; complete T047–T051 in sequence for schedule, ranking, selection, API, and UI integration.

### User Story 3

Run T054–T058 in parallel. T059 and T060 can proceed together; T063–T065 can proceed in parallel after T062 defines the port, then integrate reconciliation and monitoring through T066–T075.

### User Story 4

Run T076–T079 in parallel. T080 and T081 can proceed in parallel; integrate acceptance, similarity, and validation in T082–T086.

### User Story 5

Run T088–T092 in parallel. T093, T094, and T096 touch separate security/configuration boundaries and can proceed together before T097–T101.

### User Story 6

Run T102–T105 in parallel. T106 and T107 can proceed in parallel; T108 and T109 split by runtime adapter before permission/API/UI integration.

### User Story 7

Run T115–T118 in parallel. T119 and T120 can proceed in parallel, then T121–T125 complete the scoped indexing and answer boundary.

### User Story 8

Run T126–T129 in parallel. T130 and T132 can proceed in parallel; T131, T133, and T134 split by indexing, health, and operations before API/UI integration.

## Implementation Strategy

### MVP First

1. Complete Phases 1 and 2.
2. Complete US1 and validate risk-bounded, permission-gated Trade Plans against the recording adapter.
3. Complete US2 and validate autonomous 12-lane research evidence.
4. Complete the execution core of US3 through reconciliation and kill-switch fencing.
5. Stop for the US1–US3 independent acceptance suite before connecting any live broker account.

### Incremental Delivery

1. Deliver US5 and US6 alongside the MVP so configuration and the Codex-default runtime are usable.
2. Deliver US4 before enabling any strategy that was not pre-seeded and validated.
3. Add US7 without making semantic availability a dependency of safety.
4. Complete US8 and Phase 11 for operational visibility, audit, analytics, notifications, and release evidence.

### Format Validation

Every implementation line uses the required checkbox, sequential task ID, optional `[P]` marker, user-story label only in user-story phases, and at least one exact repository path.

## Phase 12: Convergence

- [X] T148 CRITICAL Wire the production candidate-to-broker entry pipeline so eligible deterministic setups create immutable Trade Plans, revalidate every authority, persist authorization plus an idempotent command/outbox atomically, and dispatch through the selected broker adapter in `modules/trading/trade_plans.py`, `modules/trading/authorization.py`, `modules/trading/execution_store.py`, `apps/worker/app/tasks/execution.py`, and `apps/api/app/routes/automation.py` per Constitution I/II/IX, FR-004, FR-081–FR-084, FR-107, and US1/AC1 (missing)
- [X] T149 CRITICAL Replace process-local risk reservations with PostgreSQL transactional reservations, load exact typed instrument/specification authority into fresh account risk contexts, fence concurrent candidates, and implement expiry, rejection, cancellation, acceptance, partial-fill, and confirmed-position reservation transitions in `modules/risk/authority.py`, `modules/risk/reservations.py`, `modules/risk/engine.py`, `infra/migrations/versions/0012_autonomous_execution.py`, and `tests/integration/test_trade_plan_reservation_concurrency.py` per Constitution III, FR-022–FR-033, and plan: risk concurrency and conservative defaults (partial)
- [X] T150 CRITICAL Add owner-scoped read/write APIs and a configuration/operations workspace for independently versioned entry, cancellation, protection, partial-close, and full-exit permissions plus visible durable platform/account kill switches; require contextual MFA step-up and fresh broker/account health before kill-switch deactivation in `apps/api/app/routes/automation.py`, `apps/web/src/features/configuration/AutomationControls.tsx`, `apps/web/src/features/trading/TradeManagement.tsx`, and `tests/e2e/test_autonomous_execution_controls.py` per Constitution II/VIII, FR-085, FR-105–FR-106, and US1/AC3 (partial)
- [X] T151 CRITICAL Replace legacy proposal/HIL reconciliation and management writes with typed command/order/fill/position reconciliation, ambiguous and unknown-outcome fencing before retry, actual-broker authority promotion, and permission/policy/risk-revalidated cancellation, SL/TP, partial-close, and full-exit dispatch through the common execution service in `apps/api/app/routes/trade_management.py`, `modules/trading/execution.py`, `modules/trading/reconciliation.py`, `modules/trading/monitor_agent.py`, `adapters/broker/mt5_bridge/client.py`, and `apps/worker/app/tasks/execution.py` per Constitution II/IX, FR-005–FR-006, FR-087–FR-090, FR-107, and US3/AC1–AC4 (contradicts)
- [X] T152 CRITICAL Make every per-account scheduled cycle use its enabled versioned 4×3 lane matrix, persist ranked alternatives and exclusion/invalidation lineage, run the analyst/specialist/regime/critic chain, progress READY candidates automatically with same-lane fallback, remove `MARKETS_PENDING_APPROVAL` and HIL labels, and make strategy research consume the immutable typed lane/source-cut evidence directly in `apps/worker/app/tasks/research.py`, `modules/research/workflow.py`, `apps/api/app/routes/strategies.py`, `apps/worker/app/tasks/strategies.py`, and `apps/web/src/features/research/MarketSelection.tsx` per Constitution II, FR-001–FR-002, FR-041–FR-043, and US2/AC1–AC2 (contradicts)
- [X] T153 CRITICAL Implement and consume verified account/lane/capability provider bindings for all Forex, metals, cryptocurrency, and stocks × spot, CFD, and dated-futures lanes; integrate broker CFD directories, futures chain/specification authority, CoinGecko discovery, FRED, CFTC COT, calendar/news health, and configuration UI while preserving explicit safe terminal states in `adapters/market_data/research.py`, `adapters/market_data/broker_market_data.py`, `adapters/market_data/futures_reference.py`, `modules/connections/models.py`, `apps/api/app/routes/research_matrix.py`, and `apps/web/src/features/configuration/ProviderBindings.tsx` per Constitution IX, FR-034–FR-040, and US2/AC1 (missing)
- [X] T154 CRITICAL Route every required logical role's production work through an owner-scoped `AgentRuntimeRouter` execution contract that independently resolves and versions system/user prompts, enforces tool permissions, uses same-runtime fallback chains, records configured and actual runtime/model/prompt evidence, supports `stocks_research` and the non-research roles, parses LiteLLM structured responses, and synchronizes the explicit LiteLLM model catalog without reassigning Codex-default agents in `apps/agent_worker/app/main.py`, `modules/agents/runtime.py`, `modules/agents/prompts.py`, `adapters/agent_runtime/litellm/client.py`, and `apps/api/app/routes/agents.py` per Constitution VII, FR-044–FR-054, FR-101–FR-102, and US6/AC1–AC6 (contradicts)
- [X] T155 CRITICAL Implement the origin-neutral, evidence-gated DRAFT→SPECIFIED→IMPLEMENTED→BACKTESTING→VALIDATING→PAPER_TRADING→APPROVED→ACTIVE lifecycle using one typed compiler/evaluator across historical, out-of-sample, walk-forward, stress, Monte Carlo, account-policy, paper, and live evaluation; remove arbitrary transition bypasses and permit promotion only from complete compatible evidence in `apps/api/app/routes/strategies.py`, `apps/worker/app/tasks/strategies.py`, `modules/strategies/lifecycle.py`, `modules/backtesting/promotion.py`, and `tests/integration/test_strategy_validation_pipeline.py` per Constitution IV, FR-068–FR-074, and US4/AC3 (contradicts)
- [X] T156 CRITICAL Replace the empty chart projection with authoritative live/historical candles and freshness/mapping metadata, Trade Plan/fill/protection/exit/journal overlays, pan/zoom/timeframe/indicator interactions that remain operationally read-only, and a complete adjacent versioned Trade Plan in `modules/trading/charts.py`, `apps/api/app/routes/trade_management.py`, `apps/web/src/features/trading/ActiveTradeChart.tsx`, and `apps/web/src/features/trading/TradeManagement.tsx` per Constitution product constraints, FR-114–FR-117, and US3/AC5–AC6 (partial)
- [X] T157 CRITICAL Project every committed material live-trade event into immutable owner-scoped journal observations with authoritative references and observation/inference labels, generate exactly one event-range-cited terminal summary, and use a transactional outbox for generation-safe knowledge indexing and visible index status in `modules/journal/service.py`, `modules/journal/indexing.py`, `modules/knowledge/ingestion.py`, `apps/worker/app/tasks/operations.py`, and `apps/api/app/routes/operations.py` per Constitution X, FR-091, FR-110–FR-113, and US8/AC4–AC6 (missing)
- [X] T158 CRITICAL Persist structured performance observations classified exactly BACKTEST, PAPER, or LIVE; project completed versus open-trade results; calculate every required after-cost metric, uncertainty/status, period and attribution dimension with reproducible drilldown/exclusions/freshness/conversion/version metadata; and make strategy-health work create audited research or suspension actions without mutating active rules in `modules/performance/models.py`, `modules/performance/metrics.py`, `apps/worker/app/tasks/operations.py`, `apps/api/app/routes/operations.py`, and `apps/web/src/features/performance/PerformanceDashboard.tsx` per Constitution X, FR-092–FR-093, FR-118–FR-123, and US8/AC2, AC7–AC8 (partial)
- [X] T159 CRITICAL Drive a transactional notification outbox only from confirmed broker acceptance/fill revisions, deduplicate once per command/kind/revision/enabled channel, distinguish pending/partial/complete fills, include the required account/order/price/protection/strategy/time/Trade-Plan-link fields, and persist in-product plus Telegram/Pushover delivery receipts in `modules/notifications/service.py`, `apps/worker/app/tasks/operations.py`, `modules/trading/reconciliation.py`, and `apps/api/app/routes/operations.py` per Constitution X, FR-098, FR-124, and US3/AC7 (missing)
