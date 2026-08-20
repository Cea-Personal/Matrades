# Requirements traceability

Validated on 2026-08-20. The functional requirement ranges below cover every requirement from
FR-001 through FR-105 without a gap. Task checkboxes remain the authoritative unit-level ledger.

## Functional requirements

| Requirement range | Implementation tasks | Primary implementation | Passing automated evidence |
|---|---|---|---|
| FR-001–FR-007 identity and access | T015–T036, T251–T252 | identity routes/model, session middleware, authenticated shell | identity contract/security, operational-access, safe-account browser tests |
| FR-008–FR-014 account and shared risk | T037–T074 | account/risk models, calculator, policy service, MT5 reconciliation, dashboard | account/risk and broker contracts, risk properties, broker truth/reconciliation tests |
| FR-015–FR-029 market intelligence | T075–T096, T196–T208 | ingestion, quality, eligibility, liquidity, suitability, activation, reactivation | data-quality, suitability, active-market, retention, market browser tests |
| FR-030–FR-038 strategy research/lifecycle | T097–T112, T121, T124–T125 | strategy schema/compiler/runtime, immutable lifecycle, research service | strategy runtime/lifecycle, strategy contract and browser tests |
| FR-039–FR-047 backtest/validation | T099–T101, T113–T120, T122–T123, T126–T127 | backtest execution/report, OOS, stability, Monte Carlo, chronological portfolio | reproducibility, portfolio-safety, validation contract/browser tests |
| FR-048–FR-054 paper and approval | T128–T144 | paper service/model, approval service/routes/workers/UI | paper safety, approval security/contract and browser tests |
| FR-055–FR-066 opportunity/risk decision support | T145–T163 | opportunity evaluator/ranking, shared Risk Manager, sizing, recommendation | opportunity, sizing, no-execution, fail-closed and browser tests |
| FR-067–FR-073 manual monitoring | T164–T181 | broker reconciliation, classification/matching, risk projection, frozen thesis | position classification, trade monitoring, position contract/browser tests |
| FR-074–FR-078 journal and learning | T182–T195 | journal projection, annotations, protected attachments, analytics, proposals | journal projection/learning/contract and browser tests |
| FR-079–FR-088 integrations/operations | T209–T233 | provider registry, secrets, jobs, notifications, health, audit, operations UI | integration/job/notification/audit contract/integration/browser tests |
| FR-089–FR-094 security, UI, evidence, AI boundary | T015–T036, T209–T249, T251–T252 | authorization/audit, current UI, recovery, observability, negative capabilities | hardening, audit integrity, constitutional, accessibility and system-operation tests |
| FR-095 fixed official source authority and semantics | T262–T270, T271–T293 | reviewed catalogue, MT5 evidence, CME/Cboe/Coinbase adapters, mappings, manifests, quality/fallback | specialist contract, source-authority, liquidity, fallback and MT5 safety tests |
| FR-096 asset-aware deterministic gates | T273–T275, T289–T293 | broker veto, actual/proxy/unavailable evidence, Commodity/Forex/Crypto liquidity, unchanged suitability | data-quality, asset-liquidity, acceptance and constitutional tests |
| FR-097 durable anchored automation | T265–T266, T276–T277, T298–T303 | schedule/occurrence/parent/children, DST due math, unique claims, overlap skip, scanner/leases | scheduler and coordinated-run integration tests |
| FR-098 exactly-three coordinated outcomes | T277, T300–T304, T307–T309 | parent constraint, independent category children/outcomes, durable history/report and embedded Markets UI | coordinated/API/Playwright journeys and acceptance test |
| FR-099 global reviewed LLM selection | T265, T267, T278, T294–T298, T304, T306–T309 | future-run configuration, exact pin, strict schema, OpenAI/Anthropic adapters | LLM-boundary and automation API tests |
| FR-100 deterministic authority over LLM | T278, T294–T297, T309, T321–T322 | minimized prompt, no tools, strict advisory output, immutable deterministic hash | LLM-boundary, static negative-capability and acceptance tests |
| FR-101 bounded same-source fallback | T269, T275, T288–T293, T301 | specialist retry → current MT5 → originally-fresh cache → block | fallback safety and acceptance tests |
| FR-102 reviewed provider operations | T311–T320 | catalogue-bound encrypted/idempotent lifecycle, qualification/health, existing Integrations/System UI | provider contract/security and passing provider Playwright journey |
| FR-103 source/model/schedule evidence visibility | T304–T310, T319–T320 | coordinated history/report, Instrument Library, System health, durable notifications | API contract, strict web checks, passing market/accessibility journeys |
| FR-104 human activation/replacement separation | T293, T300, T304, T308–T309, T321–T322 | proposal-only category results, preserved active assignment, existing approval component | acceptance/constitutional tests and active-market tests |
| FR-105 retained evidence and recovery | T264–T266, T288–T305, T325–T329 | immutable manifests/raw hashes, pins/attempts/events, leases, operator recovery runbook | migration, scheduler, backup/recovery and acceptance tests |

## Success criteria

`PASS (automated)` means the deterministic acceptance boundary has passing evidence. `OPEN` means
the success criterion requires external timing, moderated users, or unresolved contract work and
must not be represented as production evidence.

| Criterion | Implementation/tasks | Evidence and status |
|---|---|---|
| SC-001 owner reaches populated Command Center in 15 minutes | T030–T035, T037–T074, T252 | Authentication/account browser flows pass; 90% first-user timed study OPEN |
| SC-002 unauthorized access/actions denied and recorded | T015–T027, T251 | operational route, RBAC, audit tests — PASS (automated) |
| SC-003 ordinary dashboard refresh within 5 seconds | T055, T058, T239 | dashboard projection performance test — PASS (automated); production 95th percentile OPEN |
| SC-004 complete market-universe evidence | T075–T096 | market contracts, suitability and browser report — PASS (automated) |
| SC-005 mandatory failures excluded before rank | T075–T096, T234–T235 | data-quality, suitability, constitutional tests — PASS (automated) |
| SC-006 exactly three explicit active categories | T039, T075–T096, T235 | active-market safety and browser tests — PASS (automated) |
| SC-007 lifecycle evidence and human approval | T098, T111, T128–T144, T235 | lifecycle, paper-promotion and approval tests — PASS (automated) |
| SC-008 reproducible strategy evidence | T097, T099–T100, T108–T120 | reproducibility and validation suites — PASS (automated) |
| SC-009 third/dynamic-capacity/LOCKDOWN blocks | T041, T101, T119, T145–T163, T235 | risk, portfolio and constitutional tests — PASS (automated) |
| SC-010 invalid critical data issues no recommendation | T041, T146, T153–T154, T234–T235 | fail-closed safety tests — PASS (automated) |
| SC-011 actionable recommendation is complete | T147, T155–T160 | recommendation contract and browser tests — PASS (automated) |
| SC-012 broker changes visible within 60 seconds | T060–T073, T164–T181, T239 | reconciliation/performance fixtures pass; external MT5 95th percentile OPEN |
| SC-013 critical notifications within 60 seconds | T211–T213, T218, T223, T228–T232, T239 | routing/job performance tests pass; production providers and 95th percentile OPEN |
| SC-014 closed trade journal within 60 seconds | T182–T195, T239 | projection/analytics tests pass; external MT5 timing OPEN |
| SC-015 retained knowledge survives replacement/reactivation | T196–T208, T235 | retention/reactivation integration and constitutional tests — PASS (automated) |
| SC-016 90% moderated core-workflow completion | T103, T132, T150, T169, T185, T199, T214, T240 | 22 browser journeys pass; moderated user study OPEN |
| SC-017 no real-money execution path | T040, T148, T150, T234–T235 | static/OpenAPI/MT5/source negative-capability tests — PASS (automated) |
| SC-018 90% user explanation success | T095, T127, T160, T240 | evidence UI and accessibility journeys pass; moderated comprehension study OPEN |
| SC-019 unique browser-independent occurrences | T276–T277, T299–T303, T322–T323 | unique-claim/DST/overlap/recovery and due-math performance tests — PASS (automated); live restart drill OPEN |
| SC-020 authoritative complete source evidence | T271–T293, T310, T321–T322 | provider, mapping, MT5 veto, asset-liquidity, fallback and conflict tests — PASS (automated); production entitlements OPEN |
| SC-021 exact LLM pin and deterministic independence | T278, T294–T309, T321–T322 | invalid/rate-limit/timeout/retry tests retain deterministic hash and exact model — PASS (automated) |
| SC-022 usable three-category automation | T279–T280, T304–T310, T313, T324 | API/Vitest/lint/type/build and 22/22 Playwright journeys — PASS (automated) |

## Release consequence

All 105 functional requirements and 22 success criteria are mapped. The original market,
strategy, paper, opportunity, monitoring, journal/retention, and operations closures are backed by
persisted services, authorized routes, the current Command Center workspaces, and the automated
evidence named above; no phase creates an order or automatic lifecycle promotion.

SC-001, SC-003, SC-012–SC-014, SC-016, and SC-018 still require production-like or moderated
measurements. SC-019 needs a running restart drill and SC-020 needs legally usable production
entitlements. SC-022 now has passing browser evidence. T247/T328 documentation is complete, while
the production release remains blocked on the open external evidence.
