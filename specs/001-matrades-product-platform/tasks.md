# Tasks: Matrades Product Platform — 12-Lane Realignment

**Input**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md),
and [Constitution 2.1.0](../../.specify/memory/constitution.md)

**Scope**: This is the forward implementation backlog for the asset-class × instrument-type
realignment. It assumes the existing V1 foundation remains in place and replaces category-only
research, risk, contract, and UI paths with the typed 12-lane model. Existing historical records
must remain readable as `LEGACY_UNTYPED`; no task may infer an instrument type from a symbol.

**Tests**: Required. The specification, constitution, and quickstart define deterministic safety,
contract, migration, replay, security, browser, and release evidence as delivery gates.

**Format**: `[P]` means the task can run in parallel once its phase dependencies are met. `[USn]`
maps a task to the matching user story in `spec.md`.

## Phase 1: Setup and Contract Tooling

**Purpose**: Make the revised contracts, fixtures, and migration workflow reproducible before
domain code changes.

- [X] T001 Create deterministic OpenAPI Python/TypeScript generation and stale-output verification in `scripts/generate_contracts.py`
- [X] T002 Add a contract-generation command and generated-file verification target in `Makefile`
- [X] T003 [P] Add typed 12-lane instrument, specification, futures-chain, corporate-action, and financing fixtures in `tests/fixtures/instrument_matrix.py`
- [X] T004 [P] Add fixture account schedules and per-lane provider-binding fixtures in `tests/fixtures/research_matrix.py`
- [X] T005 [P] Add spot, CFD, futures, corporate-action, and roll replay datasets with point-in-time metadata in `tests/fixtures/instrument_lifecycle.py`
- [X] T006 Add the matrix migration test environment and forward/rollback migration harness in `tests/integration/test_matrix_migration.py`
- [X] T007 [P] Add matrix, lifecycle, migration, and generated-contract jobs to the release workflow in `.github/workflows/ci.yml`
- [X] T008 Update local development and test-service configuration for futures-chain/reference-provider fixtures in `infra/compose/compose.yaml`

**Checkpoint**: A clean checkout can generate the contracts, load deterministic 12-lane fixtures,
and exercise the expand/dual-read/new-write migration path.

## Phase 2: Foundational Typed Instrument and Compatibility Layer

**Purpose**: Establish immutable typed identities, specification authority, provider capabilities,
and compatibility primitives that block unsafe cross-type behavior in every user story.

**Critical**: Complete this phase before new typed HIL-1, HIL-2, HIL-3, strategy, or UI writes.

- [X] T009 Define canonical `AssetClass`, `InstrumentType`, quantity-unit, research-lane, and lifecycle enums in `packages/shared/domain_types.py`
- [X] T010 Extend economic-underlying, typed-instrument, venue-listing, alias, and effective specification entities in `modules/market_data/models.py`
- [X] T011 Add futures series, dated contract, continuous analytical series, chain snapshot, roll rule, corporate action, and financing-observation entities in `modules/market_data/models.py`
- [X] T012 Add versioned account research-matrix and provider-binding entities with capability, authority purpose, priority, freshness, and verification state in `modules/connections/models.py`
- [X] T013 Extend account snapshots with cash and owned-asset balances while keeping derivative exposure separate from spot inventory in `modules/accounts/models.py`
- [X] T014 Extend research runs, lane results, candidates, selections, and HIL-1 replacement lineage with typed listing/specification references in `modules/analysis/models.py`
- [X] T015 Extend candidate-risk, reservation, exposure, and result models with typed quantity, margin, notional, venue, contract, and specification references in `modules/risk/models.py`
- [X] T016 Extend broker position, broker event, reconciliation, and trade records with typed listing, contract, quantity-unit, specification, margin, and financing fields in `modules/trading/broker_models.py`
- [X] T017 Create the expand/dual-read/new-write database migration, including `LEGACY_UNTYPED` preservation and reversible indexes, in `infra/migrations/versions/0011_instrument_matrix.py`
- [X] T018 Implement legacy-record classification, provable-only backfill, and new-write typed-reference enforcement in `modules/market_data/migration.py`
- [X] T019 Extend persistence validation so executable references require a verified listing and fresh effective specification in `packages/shared/persistence.py`
- [X] T020 Implement versioned instrument-mapping, specification, lifecycle, and lane event payloads in `packages/contracts/events.py`
- [X] T021 Extend market-data capability, discovery, contract-detail, chain, corporate-action, and financing ports in `modules/market_data/ports.py`
- [X] T022 Extend the read-only broker port with typed instrument directory, quote, and symbol-detail operations in `modules/trading/broker_port.py`
- [X] T023 Implement capability-aware adapter errors that distinguish unavailable, stale, unconfigured, and blocked data in `adapters/base.py`
- [X] T024 Implement account → lane → capability → binding → healthy connection → verified mapping resolution in `modules/connections/resolution.py`
- [X] T025 Regenerate typed OpenAPI models and update contract-version assertions in `packages/contracts/generated/openapi.py` and `packages/contracts/generated/openapi.ts`
- [X] T026 Add foundational contract tests that reject missing listing/specification/contract references, cross-type substitution, and fabricated legacy typing in `tests/contract/test_instrument_matrix_foundation.py`

**Checkpoint**: New material writes use a typed lane, exact listing or dated futures contract, and
effective specification. Historical category-only facts remain readable but cannot become actionable
without explicit verification.

## Phase 3: User Story 1 — Make a Safe Trade Decision (Priority: P1) 🎯 MVP

**Goal**: Produce a deterministic HIL-2 proposal only when current account capacity and the exact
spot, CFD, or futures instrument terms make worst-case loss safe to establish.

**Independent Test**: Seed a verified typed listing and account snapshot for each instrument type.
Verify PASS, REDUCE_SIZE, and HARD_BLOCK results, including hard blocking of missing/stale terms and
cross-wrapper exposure aggregation.

### Tests for User Story 1

- [X] T027 [P] [US1] Add property tests for type-dispatched sizing, conservative rounding, and monotonic risk capacity in `tests/property/test_instrument_type_risk.py`
- [X] T028 [P] [US1] Add unit tests for spot cash/ownership, CFD lots/multiplier/financing, and futures contracts/ticks in `tests/unit/risk/test_instrument_valuation.py`
- [X] T029 [P] [US1] Add property tests for shared-underlying exposure across spot, CFD, and futures wrappers in `tests/property/test_cross_wrapper_exposure.py`
- [X] T030 [P] [US1] Add HIL-2 contract tests for required listing, specification, quantity unit, and dated-contract references in `tests/contract/test_typed_risk_api.py`
- [X] T031 [P] [US1] Add replay tests for specification changes, financing changes, and expiry-triggered revalidation in `tests/replay/test_typed_pretrade_reproducibility.py`
- [X] T032 [P] [US1] Add browser coverage for typed risk inputs, margin-versus-loss explanations, and hard-block reasons in `apps/web/src/features/risk/RiskSnapshot.test.tsx`

### Implementation for User Story 1

- [X] T033 [US1] Implement typed valuation dispatch and deterministic price/currency conversion in `modules/risk/financial_math.py`
- [X] T034 [US1] Implement spot owned-quantity/cash, CFD lot/contract, and futures contract/tick sizing with round-down recomputation in `modules/risk/position_sizing.py`
- [X] T035 [US1] Implement reserved-risk calculations that use the correct type-specific Stop Loss loss and deterministic costs in `modules/risk/reserved_risk.py`
- [X] T036 [US1] Implement underlying-level aggregation across wrappers while preserving directional and category/factor exposure in `modules/risk/exposure.py`
- [X] T037 [US1] Extend dynamic additional-trade capacity with type-specific margin, ownership, expiry, and portfolio constraints in `modules/risk/trade_capacity.py`
- [X] T038 [US1] Require fresh verified specifications, dated executable futures contracts, and type-correct broker terms in `modules/risk/authority.py`
- [X] T039 [US1] Extend the Risk Engine context/result and revalidation triggers for mapping, specification, financing, corporate-action, and expiry changes in `modules/risk/engine.py`
- [X] T040 [US1] Persist type-aware trade construction and reject any proposal whose type/listing/specification differs from its selected candidate in `modules/trading/construction.py`
- [X] T041 [US1] Extend proposal orchestration and HIL-2 state transitions to pin typed risk evidence and lifecycle triggers in `modules/trading/proposals.py` and `modules/trading/hil2.py`
- [X] T042 [US1] Implement typed risk-evaluation request/response validation and revalidation error mapping in `apps/api/app/routes/risk.py`
- [X] T043 [US1] Display quantity unit, notional, margin, maximum loss, specification provenance, and cross-wrapper exposure in `apps/web/src/features/risk/RiskSnapshot.tsx`
- [X] T044 [US1] Display the exact listing/contract, type, and risk revalidation state in `apps/web/src/features/trading/TradeProposalPanel.tsx`

**Checkpoint**: US1 permits only risk-bounded, type-correct recommendations; margin is never
treated as maximum loss, and a stale or unknown contract term cannot reach actionable HIL-2.

## Phase 4: User Story 2 — Select Markets for the Session (Priority: P1)

**Goal**: Run an account schedule across all enabled asset-class × instrument-type lanes and retain
one exact candidate or an explicit safe terminal state for every lane.

**Independent Test**: Run a fully configured account matrix and receive twelve terminal results.
Replace only one lane, approve ready lanes according to policy, and prove a missing binding or stale
provider yields a visible non-ready result without cross-type fallback.

### Tests for User Story 2

- [X] T045 [P] [US2] Add contract tests for research matrices, provider bindings, instrument discovery, and typed HIL-1 replacements in `tests/contract/test_research_matrix_api.py`
- [X] T046 [P] [US2] Add replay tests requiring exactly one terminal result for every requested lane in `tests/replay/test_twelve_lane_research.py`
- [X] T047 [P] [US2] Add adapter conformance tests for discovery, capability declarations, specifications, chains, financing, and corporate actions in `tests/contract/test_typed_market_adapters.py`
- [X] T048 [P] [US2] Add integration tests for source-cut deduplication, quotas, and account-specific eligibility in `tests/integration/test_shared_research_source_cuts.py`
- [X] T049 [P] [US2] Add failure tests for `NOT_CONFIGURED`, `UNAVAILABLE`, `STALE`, and `BLOCKED` lane outcomes in `tests/failure/test_research_lane_safe_failure.py`
- [X] T050 [P] [US2] Add browser tests for the twelve-lane result grid, lane-scoped replacement, and safe-status explanations in `tests/e2e/test_market_matrix_selection.py`

### Implementation for User Story 2

- [X] T051 [US2] Implement verified underlying, typed-instrument, venue-listing, alias, and specification repositories in `modules/market_data/instruments.py`
- [X] T052 [US2] Implement effective-dated specification validation, version activation, freshness, and audit emission in `modules/market_data/specifications.py`
- [X] T053 [US2] Implement point-in-time futures-chain capture, dated-contract eligibility, expiry notices, and explicit roll rules in `modules/market_data/futures.py`
- [X] T054 [US2] Implement point-in-time stock corporate actions and CFD financing/cash-adjustment persistence in `modules/market_data/lifecycle.py`
- [X] T055 [US2] Implement account research-matrix versioning and lane schedule normalization in `modules/research/matrix.py`
- [X] T056 [US2] Implement provider-binding CRUD, verification, authority-purpose checks, and no-cross-type fallback in `modules/connections/service.py`
- [X] T057 [US2] Implement shared provider source-cut planning, deduplication, token buckets, endpoint cost weights, and `Retry-After` handling in `modules/market_data/ingestion.py`
- [X] T058 [P] [US2] Extend Twelve Data capability declarations and typed discovery/history normalization in `adapters/market_data/twelve_data/client.py`
- [X] T059 [P] [US2] Extend Coinbase product, spot/futures discovery, quote, trade, candle, order-book, and funding normalization in `adapters/market_data/coinbase/client.py`
- [X] T060 [P] [US2] Keep CoinGecko limited to typed discovery and metadata, never executable quote authority, in `adapters/market_data/coingecko/client.py`
- [X] T061 [P] [US2] Implement broker-backed CFD directory, executable quote, and effective contract-term normalization in `adapters/market_data/broker_market_data.py`
- [X] T062 [P] [US2] Implement futures-chain/reference-provider capability adapter and exact-contract mapping in `adapters/market_data/futures_reference.py`
- [X] T063 [US2] Extend normalized observations and fingerprints with lane, listing, contract, specification, and source-cut provenance in `modules/analysis/models.py`
- [X] T064 [US2] Extend technical, macro, event, sentiment, liquidity, and regime features to preserve typed-lane evidence in `modules/analysis/technical.py`, `modules/analysis/context.py`, and `modules/analysis/regime.py`
- [X] T065 [US2] Add the protected `stocks_research` role and type-independent specialist dispatch in `modules/analysis/research_roles.py`
- [X] T066 [US2] Replace category-only ranking with independent lane ranking and terminal outcomes in `modules/analysis/daily_research.py`
- [X] T067 [US2] Replace the category-only workflow with durable lane results, typed agent context, and lane-scoped critic review in `modules/research/workflow.py`
- [X] T068 [US2] Persist immutable per-lane market-research manifests, source cuts, candidate evidence, and checksums in `modules/research/artifacts.py`
- [X] T069 [US2] Schedule account-specific matrices while reusing shared provider cuts in `modules/research/scheduling.py` and `apps/worker/app/tasks/research.py`
- [X] T070 [US2] Implement account matrix, provider-binding, instrument-directory, research-run, and lane-scoped HIL-1 endpoints in `apps/api/app/routes/research.py`
- [X] T071 [US2] Add account research-matrix and provider-binding configuration controls in `apps/web/src/features/configuration/Connections.tsx`
- [X] T072 [US2] Replace category cards with the typed 4×3 matrix, per-lane evidence, status, and replacement controls in `apps/web/src/features/research/MarketSelection.tsx`
- [X] T073 [US2] Surface lane freshness, binding, mapping, and data-capability health in `apps/web/src/features/health/HealthDashboard.tsx`

**Checkpoint**: US2 delivers a truthful daily matrix. Every requested lane is terminal, traceable,
and independently retryable; continuous futures are analytical only and never HIL-1 candidates.

## Phase 5: User Story 3 — Execute and Manage a Trade Manually (Priority: P1)

**Goal**: Reconcile a manually entered type-correct broker position and monitor it without adding a
broker write path.

**Independent Test**: TAKE a typed proposal, manually enter a matching spot, CFD, or dated-futures
position, reconcile it, and verify HIL-3 remains manual while a mismatched wrapper cannot match.

### Tests for User Story 3

- [X] T074 [P] [US3] Add bridge protocol tests for typed symbol metadata, quantity units, margin, financing, and expiry in `tests/contract/test_typed_broker_bridge.py`
- [X] T075 [P] [US3] Add exact-listing, contract, wrapper-mismatch, and ambiguous-match reconciliation tests in `tests/integration/test_typed_position_reconciliation.py`
- [X] T076 [P] [US3] Add monitoring replay tests for futures expiry/roll, corporate actions, and financing changes in `tests/replay/test_typed_trade_monitoring.py`
- [X] T077 [P] [US3] Add browser tests for typed awaiting-entry, reconciliation, and HIL-3 presentation in `tests/e2e/test_typed_manual_trade_management.py`

### Implementation for User Story 3

- [X] T078 [US3] Extend bridge account, position, symbol, event, and heartbeat schemas with typed contract metadata in `packages/broker_sdk/schemas.py`
- [X] T079 [US3] Publish MT5 symbol directory, calculation mode, contract size, tick value, bounds, swap, sessions, and expiry data in `bridges/mt5/reader.py`
- [X] T080 [US3] Expose read-only typed instrument-directory, quote, and symbol-detail endpoints from the bridge in `bridges/mt5/app.py`
- [X] T081 [US3] Validate and normalize effective broker symbol terms, typed events, and stale bridge state in `adapters/broker/mt5_bridge/client.py`
- [X] T082 [US3] Require an exact listing/dated contract and instrument type when matching manual entries in `modules/trading/reconciliation.py`
- [X] T083 [US3] Include quantity unit, specification, actual margin, financing, and contract lifecycle data in reconciled positions in `modules/trading/active_trades.py`
- [X] T084 [US3] Trigger deterministic monitoring revalidation on mapping/specification, corporate-action, financing, expiry, and roll events in `modules/trading/monitor.py`
- [X] T085 [US3] Reject HIL-3 recommendations when actual typed broker state is stale or contract identity differs in `modules/trading/hil3.py`
- [X] T086 [US3] Expose typed reconciliation detail and HIL-3 revalidation reasons in `apps/api/app/routes/trade_management.py`
- [X] T087 [US3] Display typed MT5 instrument terms, bridge metadata, and verification state in `apps/web/src/features/connections/MT5Connection.tsx`
- [X] T088 [US3] Display actual listing/contract, quantity unit, financing, lifecycle status, and manual HIL-3 controls in `apps/web/src/features/trading/TradeManagement.tsx`

**Checkpoint**: US3 never auto-executes. Actual broker values are authoritative only after a
type-correct reconciliation, and a spot/CFD/futures wrapper mismatch is never auto-matched.

## Phase 6: User Story 4 — Create and Validate a Strategy (Priority: P2)

**Goal**: Create AI-generated or AI-assisted strategy proposals from approved typed market evidence
and validate each instrument profile without silently reusing spot results for CFDs or futures.

**Independent Test**: Create a strategy from a ready lane, verify it pins evidence and an instrument
profile, then demonstrate that a futures roll or missing CFD financing blocks promotion.

### Tests for User Story 4

- [X] T089 [P] [US4] Add strategy evidence-pack tests for typed candidate, source-cut, specification, and historical-data requirements in `tests/integration/test_typed_strategy_evidence_pack.py`
- [X] T090 [P] [US4] Add replay tests for type-specific costs, corporate actions, financing, futures rolls, and continuous-series exclusion in `tests/replay/test_instrument_profile_backtest.py`
- [X] T091 [P] [US4] Add lifecycle tests proving incomplete typed validation cannot promote a strategy in `tests/integration/test_typed_strategy_validation.py`
- [X] T092 [P] [US4] Add browser tests for profile selection, lifecycle evidence, and blocked promotion reasons in `tests/e2e/test_typed_strategy_lifecycle.py`

### Implementation for User Story 4

- [X] T093 [US4] Extend strategy, version, and implementation-artifact models with typed instrument-profile and specification compatibility in `modules/strategies/models.py`
- [X] T094 [US4] Build immutable approved-market evidence packs with lane, exact listing/contract, specification, source cut, and policy context in `modules/strategies/evidence.py`
- [X] T095 [US4] Require the Strategy Researcher and Strategy Assistant to cite typed evidence packs and return safe degraded results when grounding is incomplete in `modules/strategies/ai_workflow.py`
- [X] T096 [US4] Extend taxonomy compatibility schemas for asset class, instrument type, quantity semantics, lifecycle, and costs in `packages/strategy_sdk/schema.py`
- [X] T097 [US4] Preserve typed profile dimensions through canonicalization, duplicate assessment, and version/variant decisions in `modules/strategies/fingerprints.py` and `modules/strategies/similarity.py`
- [X] T098 [US4] Compile profile-aware evaluator artifacts while keeping generated prose/code non-executable in `modules/strategies/compiler.py`
- [X] T099 [US4] Implement point-in-time profile assembly with exact listing, dated contract, calendar, FX, specification, and universe data in `modules/backtesting/replay.py`
- [X] T100 [US4] Implement type-aware spread, commission, slippage, financing, funding, multiplier, and tick-value models in `modules/backtesting/costs.py`
- [X] T101 [US4] Implement futures roll treatment and stock corporate-action treatment without using adjusted data as executable fills in `modules/backtesting/ledger.py`
- [X] T102 [US4] Add type-specific out-of-sample, walk-forward, stress, account-policy, and paper-trading gates in `modules/backtesting/validation.py`, `modules/backtesting/stress.py`, and `modules/backtesting/paper.py`
- [X] T103 [US4] Block promotion unless the complete typed profile validation evidence is present in `modules/backtesting/promotion.py`
- [X] T104 [US4] Expose typed strategy research context, profile validation, and promotion evidence in `apps/api/app/routes/strategies.py`
- [X] T105 [US4] Add typed candidate and instrument-profile selection to the strategy builder in `apps/web/src/features/strategies/StrategyBuilder.tsx`
- [X] T106 [US4] Display pinned listing/contract, costs, lifecycle events, and validation-stage evidence in `apps/web/src/features/strategies/ValidationResults.tsx`

**Checkpoint**: US4 keeps both AI origins in one lifecycle, but validation and promotion are
instrument-profile-specific, reproducible, and incapable of treating a continuous future as live.

## Phase 7: User Story 5 — Configure Accounts, Rules, and Security (Priority: P2)

**Goal**: Let a user securely configure account-level matrix schedules, provider bindings, broker
connections, rules, and data sources without exposing secrets or weakening step-up security.

**Independent Test**: Configure a prop account and a 12-lane matrix with bound sources, verify a
credential, adjust a schedule, and prove a sensitive change requires in-context MFA and is audited.

### Tests for User Story 5

- [X] T107 [P] [US5] Add configuration contract tests for matrix schedules, bindings, and capability health in `tests/contract/test_matrix_configuration_api.py`
- [X] T108 [P] [US5] Add integration tests for account-scoped schedules, binding verification, and strict provider authority in `tests/integration/test_account_matrix_configuration.py`
- [X] T109 [P] [US5] Add security tests for masked source credentials and step-up protected binding/risk mutations in `tests/security/test_matrix_configuration_security.py`
- [X] T110 [P] [US5] Add browser tests for in-place MFA delete/replace, lane schedule editing, and connection removal in `tests/e2e/test_matrix_configuration.py`

### Implementation for User Story 5

- [X] T111 [US5] Extend trading-account configuration to persist active research-matrix version and typed ownership/cash semantics in `modules/accounts/service.py`
- [X] T112 [US5] Add provider capability discovery, binding verification, and safe deletion behavior to connection management in `modules/connections/service.py`
- [X] T113 [US5] Preserve per-account matrix schedule history and next-run computation in `modules/research/scheduling.py`
- [X] T114 [US5] Add safe configuration routes for matrix, provider bindings, typed instruments, and capability tests in `apps/api/app/routes/configuration.py`
- [X] T115 [US5] Require scoped step-up grants for sensitive provider-binding, broker, rules, and credential mutations in `apps/api/app/routes/auth.py`
- [X] T116 [US5] Add masked data-source forms, capability display, test results, and local MFA mutation dialogs in `apps/web/src/features/configuration/Connections.tsx`
- [X] T117 [US5] Add account-level 4×3 schedule, enabled-lane, and provider-binding configuration controls in `apps/web/src/features/configuration/AccountRules.tsx`
- [X] T118 [US5] Show authoritative capability, freshness, source-cut, and binding status per account and lane in `apps/web/src/features/health/HealthDashboard.tsx`
- [X] T119 [US5] Record configuration, binding, schedule, and sensitive-action audit facts in `modules/observability/audit.py`

**Checkpoint**: US5 makes configuration operationally usable: every lane has visible authority and
health, secrets stay masked, and sensitive mutations receive scoped MFA where the action occurs.

## Phase 8: User Story 6 — Configure Agents Without Changing Their Authority (Priority: P2)

**Goal**: Run all sixteen logical agents on Codex by default, make LiteLLM an explicit alternative,
and give research specialists typed lane contracts without changing tool authority.

**Independent Test**: Invoke each required agent with no override, test `stocks_research` in all
three types, then explicitly assign LiteLLM to one role and confirm no automatic cross-runtime
fallback, prompt inheritance change, or permission change occurs.

### Tests for User Story 6

- [X] T120 [P] [US6] Add contract tests for the protected 16-agent registry and typed specialist lanes in `tests/contract/test_agent_matrix_registry.py`
- [X] T121 [P] [US6] Add integration tests for typed agent envelopes, same-runtime fallback, and unavailable lane handling in `tests/integration/test_typed_agent_runtime.py`
- [X] T122 [P] [US6] Add property tests for independent prompt resolution and immutable tool permissions across runtime/model changes in `tests/property/test_prompt_resolution.py`
- [X] T123 [P] [US6] Add browser tests for agent health, explicit LiteLLM opt-in, and logical-agent test execution in `tests/e2e/test_agent_matrix_configuration.py`

### Implementation for User Story 6

- [X] T124 [US6] Add protected `stocks_research` and update required-role capability declarations in `modules/agents/registry.py`
- [X] T125 [US6] Extend agent configuration models with required lane, structured-output, and type-aware capability validation in `modules/agents/models.py`
- [X] T126 [US6] Validate typed market context, exact listing/contract, specification, and source-cut references before an agent invocation in `modules/agents/runtime.py`
- [X] T127 [US6] Persist lane-aware invocation/result evidence, actual runtime/model, prompt versions, and fallback data in `modules/agents/execution_audit.py`
- [X] T128 [US6] Enforce Codex-default and explicit-only LiteLLM routing without cross-runtime fallback in `modules/agents/model_profiles.py`
- [X] T129 [US6] Extend the Codex App Server client with typed structured-output validation and safe unavailable responses in `adapters/agent_runtime/codex_app_server/client.py`
- [X] T130 [US6] Extend the LiteLLM adapter with explicit opt-in and same-runtime model capability checks in `adapters/agent_runtime/litellm/client.py`
- [X] T131 [US6] Pass typed lane envelopes from research orchestration to agent workers in `apps/agent_worker/app/main.py`
- [X] T132 [US6] Expose typed agent configuration, test-run, runtime health, and audit endpoints in `apps/api/app/routes/agents.py`
- [X] T133 [US6] Add `stocks_research`, lane requirements, runtime selection, and test controls to `apps/web/src/features/agents/AgentConfiguration.tsx`
- [X] T134 [US6] Display independently resolved system/user prompts and preserve tool-permission immutability in `apps/web/src/features/agents/PromptConfiguration.tsx`
- [X] T135 [US6] Display selected/actual runtime, fallback reason, lane execution, and unavailable status in `apps/web/src/features/health/HealthDashboard.tsx`

**Checkpoint**: US6 proves all required agents are independently configurable yet structurally
bounded: Codex is the default, LiteLLM is explicit, and no agent can relabel a lane or gain authority.

## Phase 9: User Story 7 — Retrieve Context Without Replacing Facts (Priority: P3)

**Goal**: Make typed strategy and research context retrievable with provenance while preserving the
structured instrument, risk, policy, and account authorities.

**Independent Test**: Retrieve a permitted strategy/research artifact for one typed lane, disable
knowledge retrieval, and verify HIL-2, policy, and monitoring still use only authoritative data.

### Tests for User Story 7

- [X] T136 [P] [US7] Add authorization and provenance tests for typed research and strategy knowledge in `tests/security/test_typed_knowledge_isolation.py`
- [X] T137 [P] [US7] Add failure tests proving knowledge degradation cannot fabricate listing, specification, or risk facts in `tests/failure/test_typed_knowledge_degradation.py`
- [X] T138 [P] [US7] Add browser tests for typed source provenance, archive links, and safe deletion in `tests/e2e/test_typed_knowledge_sources.py`

### Implementation for User Story 7

- [X] T139 [US7] Add lane, listing/contract, specification, source-cut, and archive metadata to knowledge documents and segments in `modules/knowledge/models.py`
- [X] T140 [US7] Preserve typed metadata and immutable source provenance through ingestion and reprocessing in `modules/knowledge/ingestion.py`
- [X] T141 [US7] Restrict typed contextual retrieval to owner/account scope and reject its use as authoritative market/risk input in `modules/knowledge/authority.py`
- [X] T142 [US7] Add typed metadata filters and retrieval-audit fields to semantic search in `modules/knowledge/search.py`
- [X] T143 [US7] Expose typed source/segment provenance and health through `apps/api/app/routes/knowledge.py`
- [X] T144 [US7] Display typed provenance, archive evidence, health, enable/disable, and delete controls in `apps/web/src/features/knowledge/KnowledgeSources.tsx`

**Checkpoint**: US7 contributes contextual evidence but cannot invent or replace an executable
instrument, source cut, account snapshot, policy result, or risk calculation.

## Phase 10: User Story 8 — Review Decisions and Performance (Priority: P3)

**Goal**: Reconstruct each decision across its typed lifecycle, distinguish performance by wrapper,
and surface operational health and approval urgency.

**Independent Test**: Complete a typed replay trade lifecycle and reconstruct the selected lane,
listing/contract, specification, risk result, approvals, actual broker facts, and outcome from UI
and journal evidence.

### Tests for User Story 8

- [X] T145 [P] [US8] Add journal reconstruction tests for typed source, contract, specification, and lifecycle evidence in `tests/contract/test_typed_journal_reconstruction.py`
- [X] T146 [P] [US8] Add performance tests separating spot, CFD, and futures metrics and lifecycle costs in `tests/property/test_typed_performance_metrics.py`
- [X] T147 [P] [US8] Add end-to-end tests for lane-aware approval inbox, health states, notifications, and audit drill-down in `tests/e2e/test_typed_review_and_performance.py`

### Implementation for User Story 8

- [X] T148 [US8] Persist typed research, specification, lifecycle, risk, agent, approval, reconciliation, and broker evidence in `modules/journal/service.py`
- [X] T149 [US8] Compute performance dimensions by asset class, instrument type, listing/contract, strategy profile, regime, account, and cost model in `modules/performance/metrics.py`
- [X] T150 [US8] Trigger strategy degradation/research actions with typed profile evidence without mutating live rules in `modules/performance/strategy_health.py`
- [X] T151 [US8] Expose lane-aware journal, performance, approval, notification, and audit queries in `apps/api/app/routes/operations.py`
- [X] T152 [US8] Display typed research-to-trade lifecycle, contract/specification provenance, and archival evidence in `apps/web/src/features/journal/JournalTimeline.tsx`
- [X] T153 [US8] Display performance filters and comparable wrapper-aware metrics in `apps/web/src/features/performance/PerformanceDashboard.tsx`
- [X] T154 [US8] Display HIL-1 lane, HIL-2 type, HIL-3 urgency, and safe-status reasons in `apps/web/src/features/approvals/ApprovalInbox.tsx`
- [X] T155 [US8] Add typed safety, lifecycle, connection, and degraded/retry notification payloads in `modules/notifications/service.py`
- [X] T156 [US8] Render typed notification evidence and deep links in `apps/web/src/features/notifications/NotificationCenter.tsx`
- [X] T157 [US8] Expose immutable research/strategy/trade artifact manifests in the Extras interface at `apps/web/src/features/extras/Extras.tsx`

**Checkpoint**: US8 provides a complete audit trail and operational view without treating a generic
symbol, a continuous future, or a degraded source as an executable fact.

## Phase 11: Polish and Cross-Cutting Release Gates

**Purpose**: Complete migration safety, contract consistency, operations, performance, and release
evidence across every story.

- [X] T158 [P] Validate and document every OpenAPI, agent, adapter, and event change against the generated clients in `tests/contract/test_openapi_matrix_consistency.py`
- [X] T159 [P] Add event-consumer idempotency and schema-overlap tests for lane, mapping, specification, corporate-action, financing, and roll events in `tests/contract/test_typed_event_contracts.py`
- [X] T160 [P] Add forward/rollback migration, legacy read, typed new-write, and no-guess backfill tests in `tests/integration/test_instrument_matrix_migration_release.py`
- [X] T161 [P] Add load/SLO tests for twelve terminal lanes within ten minutes and typed HIL-2 decisions within five seconds in `tests/integration/test_matrix_performance_slos.py`
- [X] T162 [P] Add failure-injection tests for provider quota, stale specification, unavailable agent, bridge disconnect, and roll/corporate-action invalidation in `tests/failure/test_typed_safe_failure_matrix.py`
- [X] T163 [P] Add security tests for no broker writes, no secret exposure, tenant isolation, and type-aware authorization in `tests/security/test_typed_platform_threats.py`
- [X] T164 Regenerate and commit OpenAPI boundary outputs after the API implementation is complete in `packages/contracts/generated/openapi.py` and `packages/contracts/generated/openapi.ts`
- [X] T165 Update the MT5 bridge setup, exact symbol mapping, HMAC, and Wine troubleshooting guide in `bridges/mt5/README.md`
- [X] T166 Update deployment backup, restore, migration rollback, provider quota, and contract-version runbooks in `infra/deployment/restore-runbook.md`
- [X] T167 Execute the complete quickstart validation matrix and record SC-001 through SC-015 evidence in `tests/acceptance/success_criteria.md`
- [X] T168 Run lint, Python type checks, contract tests, property/replay/integration/security/failure suites, web tests, and browser E2E from `Makefile`

## Dependencies and Execution Order

### Phase Dependencies

- Phase 1 has no prerequisite.
- Phase 2 depends on Phase 1 and blocks every user-story phase.
- US1, US2, US3, US4, US5, US6, US7, and US8 all require Phase 2.
- US1 and US2 form the MVP delivery sequence; US3 depends on typed proposals from US1 and typed listings from US2.
- US4 depends on approved typed HIL-1 evidence from US2.
- US5 provides configuration used by US1–US4 and can progress after Phase 2, but its UI integration should complete before live-connected testing.
- US6 can progress after Phase 2; typed research agent execution integrates with US2.
- US7 can progress after Phase 2 and integrates with US4; it must not block deterministic US1/US3.
- US8 depends on durable outputs from US1–US6 and may begin its read models after Phase 2.
- Phase 11 follows all selected user stories.

### User Story Dependency Graph

```text
Setup → Foundation
Foundation → US1 (typed safe HIL-2) → US3 (manual reconciliation/HIL-3) ┐
Foundation → US2 (12-lane HIL-1) → US4 (typed strategy validation)      ├→ US8 (audit/performance)
Foundation → US5 (secure configuration) ─────────────────────────────────┤
Foundation → US6 (agent runtime) ────────────────────────────────────────┤
Foundation → US7 (bounded knowledge) ────────────────────────────────────┘
```

## Parallel Execution Examples

### User Story 1

Run T027–T032 in parallel for test coverage, then parallelize T033, T035, and T036 before integrating through T039–T044.

### User Story 2

Run T045–T050 in parallel. After the typed entities and ports exist, T058–T062 are independent adapter tasks; T071 and T073 can proceed while T072 is being built.

### User Story 3

Run T074–T077 in parallel. T079 and T087 can proceed alongside bridge adapter work, then integrate reconciliation and monitoring through T081–T088.

### User Story 4

Run T089–T092 in parallel. T096, T099, and T100 can proceed in parallel after T093–T095 establish the typed strategy context.

### User Story 5

Run T107–T110 in parallel. T111–T115 are backend-safe to split by module; T116–T118 are separate UI components once their APIs are available.

### User Story 6

Run T120–T123 in parallel. T124, T128, T129, and T130 touch distinct role/runtime boundaries; T133–T135 can proceed after the API shape is stable.

### User Story 7

Run T136–T138 in parallel, then T139–T142 can split by persistence, ingestion, authority, and search before the API/UI work.

### User Story 8

Run T145–T147 in parallel. T148–T150 are independent domain work, while T152–T157 are separate UI components after operations queries are available.

## Implementation Strategy

### MVP First

1. Complete Phases 1 and 2.
2. Complete US1 to make HIL-2 type-aware and fail safe.
3. Complete US2 to create the truthful daily 12-lane research universe.
4. Validate both stories with their independent tests before any live-connected bridge testing.

### Incremental Delivery

1. Deliver secure matrix configuration (US5) and typed agent execution (US6) alongside the MVP.
2. Add manual reconciliation and HIL-3 (US3) only after typed HIL-1/HIL-2 evidence exists.
3. Add strategy profile validation (US4), then bounded typed knowledge (US7).
4. Finish the audit/performance loop (US8) and Phase 11 release gates.

### Format Validation

All 168 tasks use the required checkbox, sequential task ID, optional parallel marker, user-story label only in a user-story phase, and at least one exact repository path.
