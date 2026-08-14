# Quickstart validation results

Validated on 2026-08-14.

## Automated and local-stack evidence

| Gate | Result |
|---|---|
| Ruff lint across the repository | PASS |
| Mypy across source, API, and workers | PASS (130 source files) |
| Python unit/contract/integration/data-quality/reproducibility/safety/security/performance suite | PASS (159 tests) |
| Web TypeScript and ESLint | PASS |
| Web component suite | PASS (3 files, 3 tests) |
| Playwright integrated browser journeys | PASS (19 tests) |
| Optimized Next.js production build | PASS (10 application routes plus not-found) |
| Fresh SQLite Alembic rehearsal | PASS (`0001` through `0022_authentication_throttles`) |
| Existing PostgreSQL forward migration | PASS (`0014` through `0022_authentication_throttles`) |
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
| 1. Contracts and static quality | PARTIAL | Executable OpenAPI/provider safety passes; hand-authored HTTP and domain-event reconciliation remains open in `contracts/compatibility-report.md` |
| 2. Local validation environment | PASS | PostgreSQL, Redis, API, web, workers, scheduler, and Caddy were running; migration and HTTPS health passed |
| 3. Automated test gates | PASS | All local automated suites passed; external-provider processes are not part of the fixture suite |
| 4. Identity and safe control plane | PASS (automated) | Authentication, MFA, recovery, authorization, ETag, idempotency, account setup, and UI journeys use controlled fixtures |
| 5. MT5 and fail-closed integration | PARTIAL | Enrollment/snapshot/static safety and reconciliation tests pass; no external demo terminal was used in this pass |
| 6. Market selection | PASS (automated) | Three-category eligibility, ranking, explicit activation, and no-silent-replacement flows pass |
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

These are deliberate release gates, so T246 and production approval remain open. The passing local
results do not authorize deployment or real-money trading.
