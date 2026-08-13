# Implementation Plan: TraderX Core Platform

**Branch**: `001-traderx-core-platform` (Spec Kit feature context; current Git branch: `master`) |
**Date**: 2026-08-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-traderx-core-platform/spec.md` and the attached
TraderX Speckit Plan v1.0.0, reconciled with TraderX Constitution v1.1.0 and amended to select
OANDA v20 and MetaTrader 5 as the initial broker-account integrations.

## Summary

Build TraderX as a modular monolith with an authenticated browser UI, one application API, and
asynchronous workers sharing a deterministic domain core. PostgreSQL is the system of record;
Redis coordinates transient jobs and events but never owns financial truth. Provider adapters
normalize broker, market, economic, and notification integrations. The first broker-account
adapters are an OANDA v20 REST adapter and a MetaTrader 5 (MT5) terminal bridge; both provide
account truth only and expose no trading operation. The delivery order establishes identity,
audit, account truth, and risk controls before market selection, strategy research, paper
trading, live recommendations, monitoring, journaling, and learning.

The design has no real-money order submission capability. It admits one user-approved Commodity,
Forex pair, and Cryptocurrency pair to the active universe only after data, liquidity, execution,
broker, sizing, and prop-firm gates. One shared portfolio risk service applies the absolute
two-position ceiling, may reduce capacity to one or zero, and fails closed whenever critical data
or deterministic controls are unavailable.

Identity is a distinct, deep-linkable UI workflow: first-owner setup is available exactly once;
password authentication leads to TOTP enrollment or verification; recovery codes and an audited
authorized reset re-establish MFA without weakening it; and every operational route requires a
server-validated MFA session.

## Technical Context

**Language/Version**: Python 3.13 for the domain, API, workers, analysis, and simulations; Node.js
24 LTS with TypeScript 5.9 for the web application; SQL and YAML for migrations and contracts

**Primary Dependencies**: Next.js 16, React 19, TanStack Query, Tailwind CSS, Zod, Lightweight
Charts; FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery 5, HTTPX for the OANDA adapter, Polars,
NumPy, SciPy, pandas only at compatibility boundaries, and vectorbt behind an internal backtesting
port. The MT5 bridge is a separately deployed, small Python service that uses the official
`MetaTrader5` terminal IPC package; the core API never imports that package.

**Storage**: PostgreSQL 18 as the sole durable system of record; Redis 8 for job coordination,
short-lived caching, distributed locks, and delivery queues; object storage or filesystem-backed
artifacts only for large immutable exports and journal attachments, referenced from PostgreSQL

**Testing**: pytest, Hypothesis, pytest-asyncio, testcontainers, Ruff, mypy, and migration checks
for Python; Vitest, Testing Library, Playwright, ESLint, and TypeScript checks for the web;
contract, integration, reproducibility, safety, security, data-quality, and end-to-end suites

**Target Platform**: Linux server deployed as containers behind HTTPS; evergreen desktop and
mobile browsers; workers and scheduled monitoring continue independently of browser sessions. The
MT5 bridge initially runs beside one provisioned MT5 terminal on a managed Windows host, connected
to TraderX over mutually authenticated HTTPS; Docker/headless MT5 is release-blocked pending a
separate proof of compatibility.

**Project Type**: Authenticated web application with a modular-monolith backend and separately
scalable asynchronous worker processes

**Performance Goals**: At least 95% of Command Center refreshes complete within 5 seconds; at
least 95% of supported broker position changes affect risk and capacity within 60 seconds; at
least 95% of critical notifications dispatch within 60 seconds; deterministic risk decisions
complete within 1 second once required snapshots are locally available; job progress becomes
visible within 5 seconds

**Constraints**: Fail closed for missing, stale, contradictory, or unverified critical data;
maximum three active category slots and two live positions; one primary live account in V1;
manual real-money execution only; no production scraping; immutable strategy versions and trade
theses; UTC storage with explicit account reset time zone; decimal arithmetic for money, price,
size, and risk; all ordinary operation through the authenticated UI; initial owner setup is
one-time and UI-only; sessions expire after 30 idle minutes or 12 absolute hours; password reset
requires TOTP or a one-time recovery code before an operational session is issued. A new OANDA
connection defaults to `PRACTICE`; enabling `LIVE` is explicit. MT5 credentials are restricted to
an investor/read-only password and remain inside the isolated bridge, which must reject any
terminal that reports trading as permitted.

**Scale/Scope**: One manual trader or small role-controlled team, one live account, three active
markets, up to 10,000 catalogued instruments, tens of millions of time-series observations,
hundreds of strategy versions, and tens of concurrent long-running research or validation jobs;
94 functional requirements across identity, risk, markets, research, validation, paper trading,
recommendations, monitoring, journal, integrations, and audit

## Constitution Check

*GATE: Passed before Phase 0 research. Re-checked and passed after Phase 1 design.*

| Constitutional gate | Design evidence | Status |
|---|---|---|
| Capital preservation and Risk Manager veto | A pure deterministic risk decision service is the final live-recommendation gate; missing truth activates circuit breakers. | PASS |
| Mandatory evidence lifecycle | Strategy transition rules require research, realistic historical testing, unseen-data validation, robustness, portfolio simulation, paper evidence, and human approval. | PASS |
| Manual real-money execution | Broker ports expose account, market, position, and deal reads only; no live order command exists in application or provider contracts. | PASS |
| Broker credentials and provider boundaries | OANDA uses a GET-only endpoint allowlist despite a potentially broad PAT; MT5 runs behind an mTLS read-only terminal bridge and requires an investor password plus `trade_allowed = false`. Both fail to `LOCKDOWN` on incomplete verification. | PASS |
| Volatility plus deep-liquidity selection | Mandatory data, liquidity, execution, prop-firm, and sizing gates precede multi-horizon volatility and suitability scoring. | PASS |
| Shared equity and dynamic 0/1/2 capacity | One account aggregate owns risk snapshots; serializable decision transactions and invariants block a third live position. | PASS |
| Authenticated and UI-first operation | Dedicated setup, sign-in, MFA, reset, and recovery routes use server-validated MFA sessions; every ordinary workflow has an authenticated UI/API contract and workers continue after the browser closes. | PASS |
| Permanent knowledge and immutable versions | Instrument records are never cascade-deleted; strategy versions, run inputs, reports, decisions, and theses are append-only. | PASS |
| Deterministic, explainable, auditable safety | Versioned rule inputs produce reason-coded outputs; high-risk commands require authorization, confirmation, reason, and audit. | PASS |
| Official normalized data and fail-safe behavior | Provider ports admit only approved official connections/datasets, normalize quality metadata, and block live decisions when stale. | PASS |
| Monitoring never rewrites history | Trade thesis snapshots are immutable; monitoring observations and journal annotations append separately. | PASS |

### Post-Design Re-evaluation

The data model makes safety evidence durable, including singleton owner bootstrap, sessions,
factors, recovery, reset, and audit state. The HTTP and UI contracts separate authentication
stages from operational access and opportunity score from risk authorization; the event contracts
use transactional outbox delivery, and the broker port deliberately omits order submission. OANDA
reconciliation commits its transaction cursor only with a validated normalized snapshot; the MT5
bridge accepts only an investor-password terminal with trading disallowed and publishes complete
snapshots over mTLS. No design artifact introduces a constitutional exception.

## Project Structure

### Documentation (this feature)

```text
specs/001-traderx-core-platform/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── auth-ui.md
│   ├── http-api.yaml
│   ├── domain-events.md
│   └── provider-ports.md
├── checklists/
│   └── requirements.md
└── tasks.md                 # Created later by $speckit-tasks
```

### Source Code (repository root)

```text
apps/
├── web/
│   ├── src/app/
│   ├── src/features/
│   ├── src/components/
│   ├── src/lib/
│   └── tests/
├── api/
│   └── traderx_api/
│       ├── routes/
│       ├── auth/
│       ├── dependencies/
│       └── middleware/
└── worker/
    └── traderx_worker/
        ├── tasks/
        ├── schedules/
        └── runtime/

src/traderx/
├── identity/
├── accounts/
├── risk/
├── integrations/
├── market_data/
├── instruments/
├── market_research/
├── research/
├── strategies/
├── backtesting/
├── validation/
├── paper/
├── opportunities/
├── portfolio/
├── monitoring/
├── journal/
├── notifications/
├── audit/
├── jobs/
└── shared/

migrations/
tests/
├── unit/
├── contract/
├── integration/
├── reproducibility/
├── safety/
├── security/
├── data_quality/
└── e2e/

deploy/
├── compose.yaml
├── containers/
└── proxy/
```

**Structure Decision**: Use one repository and one Python domain package shared by the API and
worker entry points. Domain modules own rules and ports; adapters live at module edges. The web
application consumes the versioned HTTP contract. This preserves modular-monolith deployment and
avoids network boundaries between financial rules while allowing web, API, and workers to scale
as separate processes.

## Architectural Decisions

### Domain and Transaction Boundaries

- PostgreSQL is authoritative for users, configuration, evidence, jobs, account snapshots,
  positions, recommendations, audits, and outbox events. Redis state is reconstructable.
- Commands mutate one domain aggregate per transaction. Cross-domain reactions use an append-only
  transactional outbox and idempotent consumers.
- High-risk commands carry an idempotency key, expected aggregate version, actor, confirmation,
  and reason. Optimistic concurrency rejects stale UI decisions.
- Monetary and instrument values use fixed-precision decimal types. Binary floating point is
  confined to analytical arrays and converted through explicit, tested boundaries.
- All timestamps are timezone-aware UTC. Account daily reset rules retain their named time zone
  and daylight-saving interpretation.

### Provider Isolation

- Broker, market-data, economic-data, notification, artifact, and clock ports are defined by the
  domain and implemented by adapters.
- Broker capabilities are explicitly allowlisted. V1 supports account, symbol, quote, position,
  and historical-deal reads; live order create/change/cancel methods do not exist.
- Raw provider payloads may be retained for reconciliation, but domain decisions consume only
  normalized, quality-labelled records.
- Repeated and out-of-order updates are deduplicated by provider identity and sequence/time,
  reconciled against current snapshots, and never allowed to double-count exposure.

### Selected Broker-Account Adapters

- **OANDA v20** is a direct, official REST adapter. The owner creates an integration in the UI,
  chooses `PRACTICE` (the default) or explicitly confirms `LIVE`, supplies a write-only Personal
  Access Token, tests it, selects one account returned by the provider, and binds that account to
  the single TraderX live account. The adapter may issue only a reviewed GET allowlist for account,
  positions, trades, transactions, and instruments. It starts from a complete account snapshot,
  then applies account changes from the saved transaction cursor; it commits a new cursor only
  after validation and falls back to a full snapshot after any gap or invalid cursor.
- **MT5** is not treated as a broker-hosted REST API. A dedicated bridge runs beside one provisioned
  MT5 terminal and communicates with TraderX only through a narrow mutually authenticated HTTPS
  contract. The bridge keeps the terminal's investor/read-only password locally; the core service
  stores only the bridge registration/client secret. At connection and on every poll it verifies
  terminal connectivity, exact account login/server, and that both terminal and account report
  trading disallowed. It publishes complete account, position, deal, and instrument snapshots;
  a failed or partial poll never means “no positions.”
- Both adapters use a single-flight normal poll target of 15 seconds, bounded retries/backoff, and
  periodic full reconciliation. Snapshot age, provider identity, schema validity, cursor/window
  continuity, and completeness are risk inputs. Any failure degrades the integration and leaves
  the account in `LOCKDOWN` until a fresh authoritative reconciliation succeeds through the
  configured breaker lifecycle.
- OANDA's public v20 documentation does not establish a customer-configurable read-only PAT. That
  capability is a release gate, not an assumption: the application enforces read-only behavior
  independently and production launch requires written provider confirmation or an equivalent
  compensating control approved by the security review.

### Quantitative Reproducibility

- Each run freezes strategy version, dataset manifest, provider/time coverage, quality report,
  parameters, execution-cost model, risk policy version, engine version, code revision, and random
  seed.
- Vectorized tools accelerate research and candidate screening. A TraderX-owned chronological
  portfolio simulator remains the qualification authority for fills, shared equity, stops,
  capacity, prop rules, and signal competition.
- Paper and live-signal evaluation use the same deterministic strategy interpreter as historical
  testing. Divergence is measured and blocks promotion when thresholds fail.
- Market Suitability versions preserve raw metrics, normalized components, weights, gate results,
  final score, rank, and explanation.

### Security and Audit

- Use server-managed, secure, HttpOnly, SameSite session cookies with short-lived sessions and
  server-side revocation; enforce 30-minute idle and 12-hour absolute expiry on every request; do
  not place durable bearer credentials in browser storage.
- Passwords use Argon2id with parameters recorded for future rehash. TOTP secrets and integration
  credentials use envelope encryption with versioned keys and masked presentation. TOTP recovery
  codes are shown once, stored only as slow hashes, and cause full session revocation plus fresh
  enrollment when redeemed.
- Provide distinct web routes for `/sign-in`, `/setup`, `/mfa/enroll`, `/mfa/verify`,
  `/password-reset`, and `/mfa-recovery`. A password-reset token can change a password but cannot
  establish an operational session without TOTP or a recovery code. Assisted MFA reset requires
  recent `OWNER`/`ADMIN` MFA, confirmation, reason, full target-session revocation, and audit.
- CSRF protection, rate limiting, content-security policy, secure headers, authorization at the
  domain command boundary, dependency scanning, and permission tests are mandatory.
- Audit records are append-only and redact secrets while retaining actor, reason, correlation,
  previous/new values, and outcome.

## Delivery Sequence

### Milestone 1 — Secure Control Plane and Risk Foundation

Deliver repository/runtime setup, public landing, dedicated `/setup`, `/sign-in`, `/mfa/enroll`,
`/mfa/verify`, `/password-reset`, and `/mfa-recovery` screens; singleton initial-owner bootstrap;
password reset; TOTP and recovery-code enrollment/recovery; assisted MFA reset; RBAC; 30-minute
idle/12-hour absolute sessions; audit framework; one trading account, prop-firm profiles, internal
policies, account snapshots, risk states, dynamic 0/1/2 capacity, circuit-breaker foundation,
UI-managed integrations, health, and deployment/CI scaffolding. The integration UI supports the
provider-specific configuration and verification states needed by OANDA account selection and MT5
bridge registration; neither path can become risk-authoritative until the broker adapters arrive
in Milestone 2 and produce a complete validated snapshot.

Exit gate: a first owner can establish and recover MFA through the UI, then configure the account
entirely through the UI. Deterministic tests prove duplicate bootstrap is impossible; reset/recovery
never bypasses MFA; expiry rejects mutations; stricter internal limits win; accumulated loss never
increases risk; unknown equity produces zero capacity; and no configured but unverified broker
connection can make an account active.

### Milestone 2 — Broker and Market Intelligence Foundation

Deliver the OANDA v20 and MT5 terminal-bridge read-only account-truth slices, normalized
market-data contracts, incremental historical sync, freshness/quality tracking, Instrument
Library, alias mapping, eligibility gates,
multi-horizon volatility/liquidity measures, versioned suitability scoring, three active slots,
human selection/replacement, and inactive-market research.

Exit gate: each selected broker has completed a current, coherent account/position/deal
reconciliation within the freshness SLO before it can provide risk truth; category reports rank
only eligible candidates; one user-approved instrument may occupy each category; replacing a
market preserves all knowledge; manually opened positions are visible.

### Milestone 3 — Strategy Research and Validation Platform

Deliver research job management, experiment evidence, canonical strategy representation, visual
builder, immutable versions, chronological backtesting, reports, out-of-sample and walk-forward
validation, parameter stability, Monte Carlo/sequence risk, and prop/portfolio simulation.

Exit gate: the same strategy version is reproducible across runs; invalid transitions fail;
profitable-but-fragile or portfolio-unsafe strategies cannot progress.

### Milestone 4 — Paper Trading and Human Promotion

Deliver current-data simulated execution, paper portfolio/journal, production-equivalent strategy
and risk logic, paper-versus-backtest comparison, configurable evidence gates, approval review,
reauthentication/MFA for approval, and audited approve/reject/research outcomes.

Exit gate: passing evidence ends at `AWAITING_APPROVAL`; no automatic live promotion exists.

### Milestone 5 — Live Decision Support

Deliver opportunity evaluation/ranking, deterministic portfolio Risk Manager, correlation and
common-factor assessment, hard two-position enforcement, decimal position sizing, complete
recommendations, reason codes, expiration/invalidation, and opportunities UI states.

Exit gate: 100-score opportunities can be blocked; third positions always fail; missing critical
data yields no recommendation; the codebase exposes no live order submission path.

### Milestone 6 — Monitoring, Journal, Alerts, and Operations

Deliver broker-position reconciliation, recommendation matching, discretionary classification,
frozen thesis, health monitoring, strategy suspension, journal and behavioral annotations,
analytics, channel-independent notifications, web/email/Telegram delivery, job operations,
structured logs, metrics, error tracking, and complete audit views.

Exit gate: position changes update risk within the success threshold; the thesis remains immutable;
existing positions stay monitored after strategy suspension; critical events notify and audit.

### Milestone 7 — Learning, Reactivation, and Market Rotation

Deliver rolling strategy health, journal-derived research proposals, periodic market-universe
reruns, explainable replacement recommendations, incremental instrument reactivation, staleness
classification, selective revalidation, historical knowledge reuse, and final security,
performance, resilience, and usability hardening.

Exit gate: deactivation/reactivation loses no evidence, stale approval never resumes automatically,
and the complete user lifecycle passes end to end through the web UI.

## Testing and Release Gates

Every milestone requires unit, contract, integration, and user-flow tests appropriate to its
scope. The following safety tests are release-blocking:

1. zero, one, and two open positions produce correct capacity; every attempted third is blocked;
2. deteriorating equity/risk moves capacity from two to one to zero without recovery sizing;
3. a discretionary broker position consumes shared risk immediately;
4. stale broker data, unknown equity, missing contract details, and failed risk evaluation block
   new recommendations while safe monitoring continues;
5. ineligible instruments never enter volatility ranking and rankings never replace markets;
6. failed historical, unseen-data, robustness, portfolio, or paper evidence cannot progress;
7. editing a validated/live strategy produces a new immutable version;
8. no unapproved or stale strategy generates an actionable live recommendation;
9. removing/reactivating instruments preserves and reuses evidence without automatic live status;
10. authentication, authorization, dedicated authentication route guards, one-time owner setup,
    MFA/reauthentication, recovery-code single use, password-reset second proof, 30-minute
    idle/12-hour absolute session expiry, CSRF, secret masking, session revocation, and audit
    requirements hold for every high-risk command;
11. duplicate/out-of-order provider updates do not duplicate positions, trades, alerts, or risk;
12. no application, contract, worker, or integration path can submit a live real-money order;
13. production connector registration rejects scraping-based providers;
14. backtest and Monte Carlo runs reproduce identical results for identical frozen inputs/seeds;
15. provider and worker failures recover idempotently without losing durable work or outbox events.
16. OANDA refuses every non-GET request, never advances a transaction cursor after a failed
    normalization, and performs a full bootstrap after cursor recovery; MT5 rejects a terminal
    with a mismatched account/server, disconnect, missing response, or any trading-enabled flag.

Production promotion also requires migration rehearsal, backup/restore validation, secret rotation
validation, accessibility and usability checks, dependency/security scans, and a documented
rollback that preserves financial and audit evidence.

## Complexity Tracking

No constitutional violations or unjustified complexity exceptions are present. The three runtime
processes are deployment roles around one modular application and one shared domain core, not
independent microservices.
