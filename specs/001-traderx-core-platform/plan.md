# Implementation Plan: TraderX Core Platform

**Branch**: `001-traderx-core-platform` (Spec Kit feature context; current Git branch: `master`) |
**Date**: 2026-08-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-traderx-core-platform/spec.md` and the attached
TraderX Speckit Plan v1.0.0, reconciled with TraderX Constitution v1.1.0 and amended for the
native MetaTrader 5 bridge, layered low-cost market-data catalogue, official-source economic-event
calendar, durable coordinated research schedule, and owner-selectable advisory LLM model.

## Summary

Build TraderX as a modular monolith with an authenticated browser UI, one application API, and
asynchronous workers sharing a deterministic domain core. PostgreSQL is the system of record;
Redis coordinates transient jobs and events but never owns financial truth. Provider adapters
normalize broker, market, economic, LLM, and notification integrations. The broker adapter is the
native outbound MetaTrader 5 (MT5) Expert Advisor; it provides account truth, the broker-supported
universe, instrument specifications, and broker-specific quote/activity evidence while exposing no
trading operation. MT5 provides broker-proxy Forex and commodity evidence, Coinbase Exchange is
the crypto venue authority, and Twelve Data supplies field-level aggregated fallback evidence only
where it actually supplies a complete fresh field. A PostgreSQL-authoritative scheduler starts one
coordinated three-category run, and a single owner-selected, run-pinned LLM provides
non-authoritative analysis without controlling any gate, metric, score, rank, or proposal.

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
Charts; FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery 5, HTTPX for reviewed market-data and
LLM adapters, Polars,
NumPy, SciPy, pandas only at compatibility boundaries, and vectorbt behind an internal backtesting
port. The MT5 bridge is `TraderXReadOnlyBridge.mq5`, compiled and attached inside the user's MT5
terminal; the API and workers never import the `MetaTrader5` Python package.

**Storage**: PostgreSQL 18 as the sole durable system of record; Redis 8 for job coordination,
short-lived caching, distributed locks, and delivery queues; object storage or filesystem-backed
artifacts only for large immutable exports and journal attachments, referenced from PostgreSQL

**Testing**: pytest, Hypothesis, pytest-asyncio, testcontainers, Ruff, mypy, and migration checks
for Python; Vitest, Testing Library, Playwright, ESLint, and TypeScript checks for the web;
contract, integration, reproducibility, safety, security, data-quality, and end-to-end suites

**Target Platform**: Linux server deployed as containers behind HTTPS; evergreen desktop and
mobile browsers; workers and scheduled monitoring/research continue independently of browser
sessions. The native MT5 EA runs inside a user-controlled MT5 terminal on macOS or Windows and
makes outbound HTTPS requests authenticated by its enrolled bearer credential.

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
requires TOTP or a one-time recovery code before an operational session is issued. MT5 credentials
remain inside MT5, which must be signed in with investor/read-only authorization and report trading
disabled. Market-data and LLM providers are deny-by-default reviewed catalogue entries with
owner-managed credentials and explicit licensing/retention status. LLM output is structured,
advisory, tool-free, and incapable of changing deterministic financial results.

**Scale/Scope**: One manual trader or small role-controlled team, one live account, three active
markets, up to 10,000 catalogued instruments, tens of millions of time-series observations,
hundreds of strategy versions, and tens of concurrent long-running research or validation jobs;
107 functional requirements and 22 success criteria across identity, risk, markets, research,
validation, paper trading, recommendations, monitoring, journal, integrations, and audit

## Constitution Check

*GATE: Passed before Phase 0 research. Re-checked and passed after Phase 1 design.*

| Constitutional gate | Design evidence | Status |
|---|---|---|
| Capital preservation and Risk Manager veto | A pure deterministic risk decision service is the final live-recommendation gate; missing truth activates circuit breakers. | PASS |
| Mandatory evidence lifecycle | Strategy transition rules require research, realistic historical testing, unseen-data validation, robustness, portfolio simulation, paper evidence, and human approval. | PASS |
| Manual real-money execution | Broker ports expose account, market, position, and deal reads only; no live order command exists in application or provider contracts. | PASS |
| Broker credentials and provider boundaries | The native MT5 EA enrolls outbound, never receives or stores an order capability, and requires investor authorization plus disabled account/terminal trading. It fails to `LOCKDOWN` on incomplete verification. | PASS |
| Volatility plus deep-liquidity selection | MT5 broker eligibility precedes asset-aware data/liquidity/execution/prop/sizing gates. Coinbase venue evidence, MT5 broker-proxy evidence, and field-level Twelve Data aggregated fallback retain explicit unchanged semantics and freshness limits before multi-horizon scoring. | PASS |
| Shared equity and dynamic 0/1/2 capacity | One account aggregate owns risk snapshots; serializable decision transactions and invariants block a third live position. | PASS |
| Authenticated and UI-first operation | Dedicated setup, sign-in, MFA, reset, and recovery routes use server-validated MFA sessions; every ordinary workflow has an authenticated UI/API contract and workers continue after the browser closes. | PASS |
| Permanent knowledge and immutable versions | Instrument records are never cascade-deleted; strategy versions, run inputs, reports, decisions, and theses are append-only. | PASS |
| Deterministic, explainable, auditable safety | Versioned rule inputs produce reason-coded outputs. The pinned LLM may explain but cannot alter eligibility, metrics, scores, ranks, proposals, risk, or approval. | PASS |
| Official normalized data and fail-safe behavior | Fixed reviewed catalogues admit only official connections/datasets, preserve venue/capability/actual/proxy provenance, apply MT5-then-fresh-cache fallback, and block an unresolved category. | PASS |
| Scheduled research and human activation | A database-authoritative schedule produces one coordinated run or one durable overlap skip; category recommendations never activate or replace a market automatically. | PASS |
| Monitoring never rewrites history | Trade thesis snapshots are immutable; monitoring observations and journal annotations append separately. | PASS |

### Post-Design Re-evaluation

The data model makes safety evidence durable, including singleton owner bootstrap, sessions,
factors, recovery, reset, and audit state. The HTTP and UI contracts separate authentication
stages from operational access and opportunity score from risk authorization; the event contracts
use transactional outbox delivery, and the broker port deliberately omits order submission. The
native MT5 EA accepts only its enrolled account/server identity with trading disallowed and
publishes complete snapshots over outbound HTTPS. Market-data and LLM catalogues are deny-by-default;
each run freezes source, policy, model, and fallback evidence. No design artifact introduces a
constitutional exception.

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
│   ├── provider-ports.md
│   └── market-research-ui.md
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
├── llm/
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

### Provider Isolation and Reviewed Catalogues

- Broker, market-data, economic-data, LLM-analysis, notification, artifact, and clock ports are
  defined by the domain and implemented by adapters.
- Every provider integration references a reviewed catalogue entry and adapter revision declaring
  configuration/credential schema, asset/venue coverage, capability, authoritative or proxy
  semantics, freshness/retry policy, retention/licensing constraints, and lifecycle. Provider
  discovery endpoints test credential access only; they never auto-admit arbitrary sources/models.
- Broker capabilities are explicitly allowlisted. V1 supports account, symbol, quote, position,
  and historical-deal reads; live order create/change/cancel methods do not exist.
- Raw provider payloads may be retained for reconciliation, but domain decisions consume only
  normalized, quality-labelled records.
- Repeated and out-of-order updates are deduplicated by provider identity and sequence/time,
  reconciled against current snapshots, and never allowed to double-count exposure.

### Selected MT5 Broker and Market-Evidence Profile

- The native `TraderXReadOnlyBridge.mq5` EA runs inside the enrolled macOS or Windows MT5 terminal
  and makes outbound HTTPS calls with a one-time enrollment followed by a rotated bearer agent
  credential. TraderX stores only credential digests; the investor password stays inside MT5.
- Every snapshot verifies the configured login/server, connection, and disabled account/terminal
  trading. It carries account, positions, overlapping deal history, the visible broker universe,
  specifications, current bid/ask/spread, broker H1 prices/tick activity, and optional broker DOM.
  Tick volume and DOM are labelled broker-specific; unsupported DOM is `UNAVAILABLE`, never zero
  and never a consolidated Forex book. Partial or failed snapshots never mean “no positions.”
- Reconciliation is single-flight with a 15-second account target, overlapping deal-ticket
  deduplication, bounded retries, and periodic full lookback. Account failures retain `LOCKDOWN`
  until a complete fresh reconciliation clears the normal breaker lifecycle.

### Layered Market-Data Authority and Fallback

- MT5 is authoritative for broker support, symbol mapping, specifications, current broker trading
  conditions, and sizing feasibility. External evidence cannot make an unsupported symbol eligible.
- `MT5_TERMINAL_BRIDGE` is the required broker authority and supplies broker-proxy Forex and
  commodity price, spread, tick-activity, execution, and available DOM evidence. A versioned
  commodity broker-proxy gate may rank and activate a broker-supported commodity, but every result
  and recommendation identifies unavailable venue volume/depth rather than claiming COMEX data.
- `COINBASE_EXCHANGE` is the cryptocurrency primary for selected-venue trade and order-book evidence.
  `TWELVE_DATA` is a reviewed Forex/crypto fallback that may provide only documented price, candle,
  volatility, volume, or liquidity fields. Every Twelve Data field is `AGGREGATED_PROXY`; it never
  represents a venue book, venue-executed volume, executable broker liquidity, or a global FX book.
  CME Group remains a disabled optional future entitlement, not a V1 requirement.
- Each category records source/venue, capability, `ACTUAL`/`BROKER_PROXY`/`AGGREGATED_PROXY`/
  `UNAVAILABLE` semantics, mapping, entitlement, quality, and policy-specific age. Initial
  freshness defaults are 60 seconds for MT5/current streams and a provider-approved bounded age
  for Twelve Data snapshots; catalogue policy versions may tighten them but outages never extend them.
- After bounded primary attempts, a category first uses complete current MT5 evidence. For an exact
  unavailable Forex or crypto field, it may then use a complete fresh Twelve Data field only if the
  pinned fallback policy permits it; otherwise it tries a still-fresh cached external dataset. No
  fallback may fill a provider-unsupported field or weaken a gate. If evidence remains insufficient,
  that category is blocked while independently valid categories complete.

### Official Economic Calendar and Event-Risk Gate

- V1 synchronizes BLS and BEA schedules from their documented machine-readable feeds and ingests
  published values from their official APIs. It ingests EIA published petroleum values from API v2;
  EIA release scheduling and FOMC schedules use owner-maintained, official-URL-cited entries when
  no documented machine feed exists. Production workers never scrape HTML.
- An owner configures high-impact event types and pre/post-event buffers. The deterministic Risk
  Manager maps events to active markets and blocks new live recommendations in the guard window;
  research, paper trading, journaling, and monitoring continue. A stale or unverified required
  event schedule inside its guard window fails closed with `CALENDAR_COVERAGE_DEGRADED`.
- Calendar imports and owner-cited overrides are append-only revisions. Every run and recommendation
  freezes the event-risk policy, event revision, official citation, source retrieval time, and
  affected-market mapping. Consensus is `UNKNOWN` in V1 unless an official source publishes it.

### Durable Coordinated Market-Research Scheduling

- PostgreSQL owns the schedule, next due time, occurrence claim, overlap decision, and run state.
  Celery Beat only wakes a due-schedule scanner. An enabled schedule uses a 1-hour-to-30-day repeat
  interval, anchored local start, and the account IANA time zone; DST calculation is versioned.
- A unique `(schedule_id, scheduled_for)` occurrence atomically creates one coordinated parent job
  with exactly three category runs, or one `SKIPPED_OVERLAP` fact. No concurrent/catch-up run is
  queued, and a lease/fencing token permits safe crash recovery without duplicate research.
- Each category freezes method and source policies independently. Completed categories may publish
  proposals while a blocked category preserves its active assignment. No run activates or replaces
  a market without a separate authorized human command.

### Advisory LLM Analysis Boundary

- A provider-neutral `LlmAnalysisPort` supports the reviewed LiteLLM Gateway adapter and a
  reviewed LiteLLM gateway adapter. The UI selects any healthy configured LLM integration and pins
  an exact model ID (or LiteLLM alias); LiteLLM owns its upstream provider routing and credentials.
- One global selection applies to all categories. A coordinated run atomically pins provider,
  exact model ID, catalogue/adapter revision, prompt template, output schema, and inference policy;
  later configuration changes affect future runs only.
- The LLM receives only bounded normalized evidence and deterministic outputs. Tools, web/file
  search, MCP, shell/code execution, account/equity data, arbitrary URLs, and credentials are absent.
  Strict structured output may contain summaries, anomalies, cautions, and method proposals only.
- TraderX owns three auditable attempts, each capped at 180 seconds and a ten-minute overall
  deadline, honoring `Retry-After`. Exhaustion marks analysis unavailable and alerts the owner;
  deterministic results still complete, no other model is substituted, and explicit retry uses the
  pinned model.

### Quantitative Reproducibility

- Each run freezes strategy version, dataset/source manifests, provider catalogue and capability
  semantics, fallback path, schedule occurrence, methodology/quality/freshness/retry policy versions,
  pinned LLM provider/model/catalogue/prompt/schema/inference versions, analysis status, engine/code
  versions, parameters, execution-cost model, risk policy, and random seed where applicable.
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
- LLM prompts exclude secrets, account identity/equity, personal data, raw integration configuration,
  and unrestricted prose. Provider retention is displayed as `STANDARD` or administrator-verified;
  `store=false` is used where supported but is never misrepresented as zero-data retention.
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
provider-specific configuration and verification states needed by MT5 bridge registration and the
reviewed catalogue; no integration becomes authoritative until its Milestone 2 adapter produces a
complete validated observation under its approved policy.

Exit gate: a first owner can establish and recover MFA through the UI, then configure the account
entirely through the UI. Deterministic tests prove duplicate bootstrap is impossible; reset/recovery
never bypasses MFA; expiry rejects mutations; stricter internal limits win; accumulated loss never
increases risk; unknown equity produces zero capacity; and no configured but unverified broker
connection can make an account active.

### Milestone 2 — Broker and Market Intelligence Foundation

Deliver the native MT5 EA account/broker-evidence slice; fixed MT5, Coinbase Exchange, Twelve Data,
and official-calendar adapters; provider/model catalogue and credential UI; normalized source,
capability, actual/proxy, mapping, freshness, conflict, and fallback evidence; incremental history;
the Instrument Library; asset-aware eligibility and multi-horizon volatility/liquidity methods; and
versioned suitability scoring. Deliver owner-configured economic-event buffers and the
database-backed anchored recurring schedule, one
coordinated three-category run, overlap skipping, three independently completable category results,
one global OpenAI/Anthropic model selector, run-level model pinning, structured advisory analysis,
and explicit same-model analysis retry inside the existing Markets workspace.

Exit gate: the selected broker has completed a current, coherent account/position/deal
reconciliation within the freshness SLO before it can provide risk truth; source-entitlement and
mapping gates pass; category reports rank only eligible candidates; exactly one due job or overlap
skip is durable; LLM output changes no deterministic result; one user-approved instrument may
occupy each category; replacing a market preserves all knowledge; manually opened positions are
visible; official or owner-cited high-impact events block affected new recommendations inside the
configured buffers; and calendar coverage degradation fails closed inside a required guard window.

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

Deliver rolling strategy health, journal-derived research proposals, results from the governed
Milestone 2 market-research scheduler, explainable replacement recommendations, incremental
instrument reactivation, staleness
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
15. provider and worker failures recover idempotently without losing durable work or outbox events;
16. MT5 rejects a terminal with a mismatched account/server, disconnect, missing response, or any
    trading-enabled flag;
17. every due research occurrence creates exactly one coordinated job or one durable overlap skip,
    never a catch-up job, and no result changes an active assignment automatically;
18. MT5-unsupported candidates are excluded even when externally covered, and every liquidity
    measure displays provider/venue plus `ACTUAL`, `BROKER_PROXY`, `AGGREGATED_PROXY`, or
    `UNAVAILABLE` semantics;
19. source failures apply bounded retries, current MT5, then only a policy-permitted fresh exact
    Twelve Data field or still-fresh cached external evidence without extending freshness;
    unresolved categories block while valid categories finish;
20. high-impact official or owner-cited events block new recommendations for their configured
    pre/post buffers, with degraded calendar coverage failing closed inside the guard window; and
21. changing the global model cannot alter an active run, and every invocation records its exact
    provider/model/catalogue/prompt/schema/inference versions; and
22. conflicting, refused, invalid, timed-out, or unavailable LLM output changes zero deterministic
    gate, metric, score, rank, or proposal values and never triggers automatic model substitution.

Production promotion also requires migration rehearsal, backup/restore validation, secret rotation
validation, accessibility and usability checks, dependency/security scans, and a documented
rollback that preserves financial and audit evidence.

## Complexity Tracking

No constitutional violations or unjustified complexity exceptions are present. The three runtime
processes are deployment roles around one modular application and one shared domain core, not
independent microservices.
