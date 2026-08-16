# Quickstart validation results

Validated on 2026-08-14.

## Automated and local-stack evidence

| Gate | Result |
|---|---|
| Ruff lint across the repository | PASS |
| Mypy across source, API, and workers | PASS (147 source files, strict mode) |
| Python unit/contract/integration/data-quality/reproducibility/safety/security/performance suite | PASS (187 tests) |
| Web TypeScript and ESLint | PASS |
| Web component suite | PASS (3 files, 3 tests) |
| Existing Playwright integrated browser journeys | PASS (19 tests, previously recorded); two amendment journeys authored but current rerun BLOCKED by local port permission |
| Optimized Next.js production build | PASS (10 application routes plus not-found) |
| Fresh SQLite Alembic rehearsal | PASS (`0001` through `0023_market_research_automation`) |
| Existing PostgreSQL forward migration | NOT RE-RUN for `0023`; Compose config and SQLite migration test pass |
| Development and production Compose rendering | PASS |
| Running local PostgreSQL and Redis health | PASS |
| Running local HTTPS `/api/v1/health` through Caddy | PASS (HTTP/2 200 with security and correlation headers) |
| Encrypted recovery manifest/checksum/tamper tests | PASS |

The PostgreSQL rehearsal exposed and corrected an Alembic revision identifier that exceeded the
database's 32-character `alembic_version.version_num` column. A regression assertion now enforces
that limit for the full migration chain.

## Validation-guide coverage

| Quickstart section | Outcome | Scope or deviation |
|---|---|---|
| 1. Contracts and static quality | PARTIAL | The amendment HTTP/provider/event boundary passes; broader hand-authored HTTP and pre-amendment event reconciliation remains open in `contracts/compatibility-report.md` |
| 2. Local validation environment | PASS | PostgreSQL, Redis, API, web, workers, scheduler, and Caddy were running; migration and HTTPS health passed |
| 3. Automated test gates | PASS | All local automated suites passed; external-provider processes are not part of the fixture suite |
| 4. Identity and safe control plane | PASS (automated) | Authentication, MFA, recovery, authorization, ETag, idempotency, account setup, and UI journeys use controlled fixtures |
| 5. MT5 and fail-closed integration | PARTIAL | Enrollment/snapshot/static safety, multi-window/activity/DOM normalization, and reconciliation tests pass; no external demo terminal was used in this pass |
| 6. Market selection | PASS (automated) | Specialist authority, source semantics, asset-aware gates, fallback, coordinated ranking, explicit activation, and no-silent-replacement flows pass |
| 7. Strategy evidence | PASS (automated) | Reproducibility, unseen data, robustness, immutable versions, and chronological shared portfolio simulation pass |
| 8. Paper and approval | PASS (automated) | Current-data simulation, evidence gates, step-up approval, and no-auto-promotion pass |
| 9. Opportunities and risk | PASS (automated) | Capacity `2 -> 1 -> 0`, veto, correlation, exact sizing, expiry, and fail-closed data pass |
| 10. Monitoring and journal | PASS (automated) | Reconciliation, frozen thesis, append-only observations, protected attachments, and analytics pass |
| 11. Reactivation and retention | PASS (automated) | Knowledge retention, missing-window refresh, staleness, revalidation, and human approval pass |
| 12. Resilience and recovery | PARTIAL | Outbox/job/recovery simulations pass; an off-host operator restore drill was not performed |

## Release gates not executed

- a real external MT5 demo terminal reconciliation and freshness/notification timing run;
- an off-host encrypted backup/restore operator drill;
- production Email/Telegram provider delivery;
- moderated usability and explanation-success studies;
- a production deployment and dynamic scan against that deployment;
- completion of the HTTP/domain-event reconciliation documented above.

## Amendment execution record (FR-095–FR-105 / SC-019–SC-022)

| Scenario | Outcome | Evidence/deviation |
|---|---|---|
| CME/Cboe/Coinbase qualification and normalized provenance | PASS (fixture contract) | `test_specialist_market_data_adapters.py`; entitlement and production licensing not exercised |
| Native MT5 multi-window/activity/real-volume/DOM evidence | PASS (static/normalization) | `test_mt5_ea_bridge.py`; real terminal run remains external |
| Broker authority, owner-approved mapping, conflict/freshness quality | PASS | `test_market_source_authority.py` and data-quality suite |
| Asset-aware Forex/Commodity/Crypto liquidity gates | PASS | `test_asset_liquidity.py`; unavailable measures fail closed |
| Three specialist attempts → MT5 → fresh cache → blocked | PASS | `test_market_source_fallback.py` and acceptance test; policy is not extended |
| One-hour/30-day anchored schedule, IANA DST, unique claim, overlap/no catch-up | PASS | scheduler integration and due-math performance tests |
| One parent/exactly three independent children and preserved assignment | PASS | coordinated-run integration and acceptance tests |
| Exact model pin, strict schema, bounded attempts, same-pin retry, immutable deterministic result | PASS | LLM-boundary safety tests |
| Authenticated schedule/model/coordinated/report/retry API | PASS | market-research automation contract test |
| Reviewed provider lifecycle, encrypted write-only secret, arbitrary URL/model rejection | PASS | provider catalogue contract/security tests |
| Existing Markets/Integrations/System UI compile and production build | PASS | Vitest, ESLint, TypeScript, Next build |
| Markets and provider browser journeys | NOT EXECUTED in this pass | Playwright could not start `127.0.0.1:3100` (`EPERM`); escalation was unavailable. Test definitions remain release-blocking. |
| Browser-closed live schedule/worker restart | NOT EXECUTED | Database scheduler logic and worker routing pass static/integration checks; running Postgres/Celery restart drill remains required |

## Existing phase closure evidence

- US2: eligibility precedes ranking, three active slots are explicit, reactivation/replacement
  retains evidence, and neither old nor amended research silently mutates assignments.
- US3: the visual strategy schema creates immutable versions and reproducible chronological
  backtest/validation evidence; failed gates cannot advance lifecycle.
- US4: current-data paper evidence ends at `AWAITING_APPROVAL`; only a fresh MFA-backed human
  decision can approve, reject, or return the version to research.
- US5: deterministic opportunities remain separate from the transactional shared-account Risk
  Manager; sizing rounds conservatively, capacity is 0–2, and blocked/no-trade states are visible.
- US6: native MT5 snapshots reconcile manual positions/deals read-only, every position enters risk,
  matching/classification is correctable, and the original thesis remains immutable.
- US7/US8: journals cover recommended/discretionary/paper outcomes, analytics can only propose
  research, and replacement/reactivation preserves aliases, strategies, tests, trades, and notes.
- US9: durable jobs, notification preferences/inbox, provider/MT5 lifecycle, health, strategy
  health, and append-only redacted audit are operated from the current authenticated UI.

The Python suite reported one dependency deprecation warning and the existing intentional audit
identity-conflict warning; Vitest emitted no test warnings. The Next build emitted a Turbopack root
warning because an unrelated parent `package-lock.json` exists outside this repository; output was
otherwise successful.

These are deliberate release gates, so T246 and production approval remain open. The passing local
results do not authorize deployment or real-money trading.
