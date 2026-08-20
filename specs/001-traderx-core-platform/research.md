# TraderX Core Platform Research

**Completed**: 2026-08-12
**Scope**: Resolve technical context, dependencies, integration patterns, and safety-sensitive
architecture choices for TraderX V1.

## 1. Runtime and Framework Baseline

**Decision**: Pin tested patch releases around Node.js 24 LTS, Next.js 16, React 19.2,
TypeScript 5.9, Python 3.13, FastAPI 0.141, Pydantic 2.13, SQLAlchemy 2.0, Alembic 1.18,
Celery 5.6, PostgreSQL 18, and Redis 8.2. Use lockfiles and container digests for exact build
reproduction.

**Rationale**: Node 24 and Next.js 16 provide the active supported web baseline. Python 3.13 is
preferred over 3.14 because Celery 5.6 documents compatibility through 3.13. PostgreSQL patch
releases remain upgrade-compatible within major 18. Exact dependency identity is also part of
quantitative-run provenance. See [Next.js support policy](https://nextjs.org/support-policy),
[Node release schedule](https://nodejs.org/en/about/previous-releases),
[Celery support](https://docs.celeryq.dev/en/stable/getting-started/), and
[PostgreSQL versioning](https://www.postgresql.org/support/versioning/).

**Alternatives considered**: Python 3.14 is deferred until the worker stack supports it. Next.js 15
has less active-support runway. Newer Redis feature releases are unnecessary for V1.

## 2. Modular Monolith with Separate Runtime Roles

**Decision**: Use one Python codebase and one shared domain core executed by API and worker
processes, plus one separate TypeScript web application. Partition the Python package into explicit
identity, account/risk, integration, market-data, instrument, research, strategy, validation,
paper, opportunity, portfolio, monitoring, journal, notification, audit, and job modules.

**Rationale**: Authoritative risk, sizing, lifecycle, and approval rules exist once, avoiding
distributed consistency and duplicated-language logic. API and worker roles can scale separately
without becoming independent services.

**Alternatives considered**: Microservices add failure modes and transactions without V1 scale.
An unstructured backend damages reviewability. Duplicating risk logic in TypeScript risks drift.

## 3. Web/API Boundary

**Decision**: Serve the web application and versioned `/api/v1` behind one HTTPS origin. Use
REST/JSON with OpenAPI 3.1 as the contract source and generated TypeScript types. Use server-sent
events for browser job progress and alerts, with polling fallback. All business commands go to the
Python application boundary; no parallel Server Action business path exists.

**Rationale**: One origin simplifies secure session cookies and CSRF controls. REST resources and
commands fit auditable workflows. SSE meets one-way progress/alert needs with less lifecycle
complexity than bidirectional sockets.

**Alternatives considered**: WebSockets and GraphQL are deferred until demonstrated requirements.
Optimistic UI success is prohibited for approval, risk, capacity, or circuit-breaker changes.

## 4. Durable Storage and Transaction Model

**Decision**: PostgreSQL is authoritative for all durable state, including sessions, financial
snapshots, jobs, evidence, approvals, audit, and outbox events. Redis is limited to transport,
short-lived caching, locks, and coordination. Use short request/task-scoped SQLAlchemy sessions,
explicit transactions, optimistic versions, fixed lock ordering for high-risk changes, database
constraints, and append-only evidence. Start with native PostgreSQL partitioning.

**Rationale**: This creates understandable failure and recovery semantics. Redis Pub/Sub is
at-most-once and cannot be the safety ledger. PostgreSQL constraints and locks provide final
defense against concurrent category, lifecycle, and risk violations. See
[PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html) and
[SQLAlchemy session guidance](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).

**Alternatives considered**: Async database access is deferred until measurement warrants it.
TimescaleDB and a separate lakehouse are deferred until native partitioning and immutable columnar
research snapshots prove insufficient.

## 5. Exact Financial Numerics and Time Semantics

**Decision**: Store money, price, profit/loss, risk, fees, contract values, and quantities as
PostgreSQL `NUMERIC` and Python `Decimal`. Construct decimals from strings/integers and apply
versioned conservative rounding; permitted volume always rounds down to a valid step. Use
floating-point arrays only for statistical analysis, followed by exact recomputation before a
safety decision.

Store event order with provider sequence and signed 64-bit UTC epoch nanoseconds where supplied;
use `timestamptz` for received/ingested operational times. Store IANA zone names and versioned
calendars for trading sessions and prop resets. Expose RFC 3339 UTC, representing nanosecond epoch
values as strings to browser clients.

**Rationale**: Exact decimal arithmetic protects financial invariants. UTC alone cannot reproduce
DST-sensitive sessions or account resets, and PostgreSQL timestamps do not preserve nanosecond
source ordering. See [PostgreSQL numeric types](https://www.postgresql.org/docs/18/datatype-numeric.html),
[Python Decimal](https://docs.python.org/3/library/decimal.html), and
[PostgreSQL date/time](https://www.postgresql.org/docs/current/datatype-datetime.html).

**Alternatives considered**: Binary float for authorization is unsafe; PostgreSQL `money` is
locale-sensitive; fixed UTC offsets do not preserve historical time-zone rules.

## 6. Canonical Market Data and Quality

**Decision**: Preserve immutable provider-native batches and produce versioned canonical
observations. Every observation identifies schema/normalization version, provider and instrument,
event and receive time, sequence/event identity, price basis, volume semantics, provenance,
revision, and quality flags. Candles use half-open intervals and correction revisions.

Use versioned quality/freshness policies by provider, data type, instrument, timeframe, and
purpose. Check schemas, contract specifications, duplicates/conflicts, sequence gaps,
calendar-aware gaps, OHLC invariants, tick/step alignment, spreads, outliers, latency, and
cross-provider contradictions. Quarantine material failures; never silently forward-fill an
executable price.

**Rationale**: Provider quirks must not leak into strategies, and freshness for a daily research
series differs from freshness for a live quote. Preserving raw evidence makes normalization errors
and provider corrections auditable.

**Alternatives considered**: Direct provider models, discarding raw inputs, one universal volume
field, one global freshness threshold, and silent repair are rejected.

## 7. Quantitative Libraries and Artifacts

**Decision**: Use Polars for tabular ingestion, validation, joins, resampling, and report
aggregation; NumPy for dense arrays and explicit random generators; SciPy for statistical tools;
and pandas only at third-party compatibility boundaries. Freeze research inputs as versioned,
content-hashed Parquet snapshots with manifests. Assert schema, time zone, null/NaN behavior,
ordering, and uniqueness at every conversion.

**Rationale**: Polars lazy scans support pushdown and streaming over data larger than memory,
while NumPy/SciPy remain mature numerical foundations. Clear ownership avoids two competing
canonical dataframe models. See [Polars lazy execution](https://docs.pola.rs/user-guide/lazy/using/).

**Alternatives considered**: pandas everywhere and Polars for every calculation are both viable
but blur ownership or impair library interoperability.

## 8. Authoritative Backtesting and Runtime Parity

**Decision**: Build a TraderX-owned deterministic chronological engine as the promotion authority.
It consumes canonical events and the same immutable strategy interpreter, sizing, Risk Manager,
cost model, and portfolio rules used by paper/live recommendation paths. Vectorbt may accelerate
screening and parameter sweeps behind an adapter, but every candidate must be rerun by the
authoritative engine.

Historical replay, current-data paper fills, and current-data recommendation-only operation are
adapters around one strategy state machine. Golden traces prove identical signals, transitions,
and risk decisions for identical events; expected differences are confined to declared execution
models. Intrabar ambiguity uses an explicit conservative policy or is reported as ambiguous.

**Rationale**: TraderX's shared-equity, dynamic capacity, prop-rule, fill, and signal-competition
semantics must have one provable source. See [vectorbt features](https://vectorbt.dev/getting-started/features/).

**Alternatives considered**: Vectorbt as sole promotion authority, separate mode implementations,
and two equally authoritative engines are rejected because disagreement would make evidence unsafe.

## 9. Reproducibility and Monte Carlo

**Decision**: Every run freezes strategy/version hash, dataset hashes, normalization/calendar/
contract versions, parameters, costs, fills, risk assumptions, engine/code/dependency/container
identity, platform details, time, and RNG metadata. Use explicit NumPy `Generator` instances and
`SeedSequence.spawn`; retain root entropy and spawn keys.

Run separately labelled sequence permutations, block/regime-aware bootstraps, cost/slippage/gap
stress, parameter-neighborhood perturbations, and full chronological shared-account paths. Report
tail distributions for drawdown, losing streak, prop breach, and ruin, not just averages.

**Rationale**: A seed alone does not reproduce results across library/platform versions, and IID
resampling destroys serial/regime dependence. NumPy does not promise identical streams across
versions. See [NumPy RNG policy](https://numpy.org/neps/nep-0019-rng-policy.html) and
[SeedSequence](https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.SeedSequence.html).

**Alternatives considered**: Mutable reports over latest data, IID-only simulations, and full
event sourcing for every product area are rejected.

## 10. Sessions, MFA, and Authorization

**Decision**: Use application-managed opaque 256-bit session tokens, storing only SHA-256 digests
in PostgreSQL. Use a `__Host-` secure, HttpOnly, Path `/`, SameSite Strict cookie; rotate at login,
MFA completion, password change, and privilege elevation. Support idle/absolute expiry and
immediate session revocation. Unsafe methods require CSRF and origin/fetch-site validation.

Hash passwords with Argon2id, beginning at 64 MiB, three iterations, one lane subject to production
benchmarking and rehash policy. TOTP uses 30-second/six-digit RFC 6238 codes with a narrow window,
replay prevention, encrypted seeds, and hashed single-use recovery codes. Require recent MFA or
reauthentication for risk relaxation, market replacement, live approval, credential rotation,
circuit-breaker override, and user/role administration.

**Rationale**: Server sessions provide immediate revocation and authentication-strength tracking.
See [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
and [RFC 6238](https://www.rfc-editor.org/info/rfc6238/).

**Alternatives considered**: Browser-stored JWTs add revocation state anyway; bcrypt and SMS MFA
are not preferred for new V1 credentials; passkeys remain future work.

## 11. Secret Protection

**Decision**: Use envelope encryption with AES-256-GCM. Store ciphertext, random nonce,
authenticated context, and key version in PostgreSQL; keep key-encryption keys outside the
database and source control. Saved secrets are write-only from the UI. Rotation supports new-key
writes, controlled old-key reads, re-encryption, revocation, and audit. Redaction covers logs,
exceptions, telemetry, job payloads, and audit values.

**Rationale**: Database-at-rest encryption does not protect a database dump from application
credential disclosure. AES-GCM supplies authenticated confidentiality. See
[OWASP cryptographic storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).

**Alternatives considered**: Custom cryptography and storing the encryption key beside ciphertext
are rejected; a full secrets platform may follow operational scale.

## 12. Versioned HTTP Contracts and Command Reliability

**Decision**: Describe one module-grouped OpenAPI 3.1 contract under `/api/v1`. Use stable unique
operation IDs, RFC 9457 `application/problem+json`, `202` plus `Location` for long jobs, domain
results for expected `BLOCKED`/`NO_TRADE`, `409` for illegal transitions or conflicting idempotency,
`428` for missing preconditions, `412` for stale `If-Match`, and `503` for an unavailable critical
safety dependency.

High-risk commands require a durable `Idempotency-Key` and `If-Match`. In one transaction, lock in
fixed order, recompute safety, mutate, append audit and outbox, and store the idempotent result.

**Rationale**: Idempotency protects ambiguous retries and entity versions prevent stale UI
decisions. See [OpenAPI](https://spec.openapis.org/oas/latest.html),
[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html), and
[HTTP conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html).

**Alternatives considered**: Client-only keys, memory caches, last-write-wins, and frontend-only
confirmation cannot protect restarts or concurrent administrators.

## 13. Outbox, Events, and Audit

**Decision**: Commit domain changes and outbox rows atomically in PostgreSQL. Dispatch pending rows
with short `SKIP LOCKED` claims and at-least-once delivery. Each consumer persists a receipt keyed
by source/event ID. Preserve per-aggregate order through aggregate version; poison events remain
visible and retryable.

Use a CloudEvents-compatible versioned JSON envelope with correlation, causation, actor, aggregate
version, and trace context. Audit is a separate append-only schema linked to events; a mandatory
audit/outbox failure aborts a high-risk change.

**Rationale**: This closes the commit/publish gap and distinguishes "what happened" from "who
attempted what under which authority and why." See
[PostgreSQL `SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html),
[CloudEvents](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md), and
[Redis Pub/Sub semantics](https://redis.io/docs/latest/develop/pubsub/).

**Alternatives considered**: Direct publish, Redis Pub/Sub as ledger, Celery-shaped domain events,
and ordinary logs as audit are rejected. Kafka and full AsyncAPI topology are premature.

## 14. Durable Jobs and Cooperative Cancellation

**Decision**: PostgreSQL `BackgroundJob` and attempt/checkpoint records are authoritative; Celery
state is diagnostic. Workers receive IDs, acquire leases/fencing tokens, checkpoint progress,
cooperatively observe pause/cancel flags, retry only transient failures with bounded backoff/jitter,
and use late acknowledgement only for proven-idempotent stages. Run separate queues for monitoring,
data, research, paper, notifications, and maintenance, with one scheduler.

**Rationale**: Celery tasks can execute more than once and hard termination can kill the wrong
work. Durable application state survives result expiry and browser closure. See
[Celery task semantics](https://docs.celeryq.dev/en/stable/userguide/tasks.html) and
[worker revocation guidance](https://docs.celeryq.dev/en/stable/userguide/workers.html).

**Alternatives considered**: Celery result state as product truth, hard termination, eager-only
testing, and unbounded retries are rejected.

## 15. Broker Reconciliation and Notifications

**Decision**: Combine low-latency streaming where supported with initial/periodic authoritative
polling and full reconciliation after reconnect or sequence gaps. Persist raw observations before
normalization. Deduplicate by provider event identity or documented fingerprint; guard projections
with sequence/revision; preserve partial fills separately. Contradictions or unresolved gaps
degrade the integration and block new recommendations.

Convert eligible domain events into immutable, channel-independent notifications and one delivery
attempt per recipient/channel. The web inbox is durable; Telegram and email are retryable targets.
External exactly-once delivery is not claimed.

**Rationale**: Streams provide latency but not recovery authority; snapshots provide truth but may
miss the 60-second target alone. Persisted routing decouples safety state from provider outages.

**Alternatives considered**: Stream-only, poll-only, timestamp-only last-write-wins, direct sending
inside business transactions, and collapsing partial fills are rejected.

## 16. Deployment, Observability, and Test Gates

**Decision**: Deploy one Linux-host Docker Compose stack: HTTPS proxy, web, API, dedicated worker
groups, singleton scheduler/outbox dispatcher, PostgreSQL, and Redis. Only the proxy exposes host
ports. Use non-root immutable images, private networks, health/readiness probes, secrets, resource
limits, one-shot migrations, encrypted off-host backups, and tested restore.

Use structured redacted logs, separate append-only audit, OpenTelemetry traces/metrics, correlation
IDs, and alerts for stale data, queue age, workers, circuit breakers, and backups. Test with Vitest,
Testing Library, Playwright, pytest, Hypothesis, real disposable PostgreSQL/Redis/workers, contract
snapshots, generated-client compilation, strict static checks, security scans, and a mandatory
safety/property suite.

**Rationale**: This is the simplest deployment meeting V1 reliability while still testing actual
transaction, queue, migration, and browser behavior. See
[Docker Compose production guidance](https://docs.docker.com/compose/how-tos/production/),
[OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/), and
[Hypothesis](https://hypothesis.readthedocs.io/en/latest/).

**Alternatives considered**: Kubernetes, public database/cache ports, mocked-only integration
tests, and eager-only worker tests are rejected.

## 17. One-Time Initial Owner Setup

**Decision**: Expose an unauthenticated `/setup` route only while a database-enforced singleton
bootstrap record does not exist. Its successful transaction creates exactly one `OWNER`, issues a
password-authenticated limited session, and requires TOTP enrollment before any operational
resource is available. Once an owner exists, setup remains unavailable even if enrollment is
interrupted; the owner resumes through `/sign-in`.

**Rationale**: This satisfies the constitution's UI-first requirement without shell, database, or
container access, while a singleton record prevents concurrent requests from creating multiple
owners.

**Alternatives considered**: CLI/database seeding, public self-registration, and external-identity
provider invitation are rejected for V1.

## 18. MFA Recovery and Assisted Reset

**Decision**: Generate recovery codes only after confirmed TOTP enrollment, show them once, and
persist only slow hashes. Recovery-code redemption atomically marks the code used, revokes all
target-user sessions, revokes or replaces the current TOTP factor with an unconfirmed enrollment,
requires new TOTP setup, and creates an audit event. When no code remains, an `OWNER` or `ADMIN`
with recent MFA may initiate the same reset using an explicit reason and confirmation; the target
has no operational session until enrollment completes.

**Rationale**: Recovery remains usable without treating email access, a stale factor, or an old
session as sufficient proof for a financial-control application.

**Alternatives considered**: Email-only recovery, reusable codes, support-only recovery, and
immediate post-reset operational access are rejected.

## 19. Deep-Linkable Authentication UI State Machine

**Decision**: Provide separate routes for `/sign-in`, `/setup`, `/mfa/enroll`, `/mfa/verify`,
`/password-reset`, and `/mfa-recovery`. Each route renders only the state valid for its short-lived
server-side challenge/session and safely redirects invalid, expired, completed, or unauthenticated
states to `/sign-in`. Protected routes reject expired sessions before invoking a mutation.

**Rationale**: Separate routes create restartable, accessible journeys, predictable browser
history, focused error states, and independently testable UI contracts.

**Alternatives considered**: A root-page wizard, modal authentication, and hosted identity UI are
rejected for V1.

## 20. Password Reset Requires a Second Proof

**Decision**: A password-reset token authorizes password replacement only. Before issuing an
MFA-assured session, require a current TOTP code or an unused recovery code. Reset tokens and
recovery codes are single-use and expiry-limited; a successful reset revokes all sessions and
records reset/recovery evidence.

**Rationale**: Possession of an email-delivered reset token alone is insufficient to restore access
to sensitive account, risk, and integration controls.

**Alternatives considered**: Automatic login after reset, password-reset-only access, and mandatory
administrator approval for every reset are rejected.

## 21. Fixed Session Expiry Semantics

**Decision**: Enforce a 30-minute inactivity limit and 12-hour absolute lifetime server-side for
every authenticated request. A request after either limit is rejected without mutation; the
cookie/session is cleared or revoked and the UI returns to `/sign-in` with an expiry explanation.
Activity may update `last_seen_at` but never `expires_at`; password, MFA, recovery, and privilege
events rotate the session and start a new absolute window.

**Rationale**: Server-side enforcement works consistently across tabs and browser closure while
providing a practical, bounded operating session.

**Alternatives considered**: Client-only timers, rolling unlimited sessions, eight-hour idle
sessions, and explicit-logout-only sessions are rejected.

## 23. MetaTrader 5 Read-Only Terminal Bridge

**Decision**: Use the native `TraderXReadOnlyBridge.mq5` Expert Advisor already delivered with
TraderX. It runs inside the user's MT5 terminal on macOS or Windows and makes outbound HTTPS calls
to a fixed TraderX API surface. An authorized owner records the login/server and receives a
single-use enrollment code; the EA exchanges it for a bearer agent credential. TraderX stores only
digests, and the investor password remains entirely inside MT5.

Every enrollment and snapshot verifies the configured login/server, terminal connection, and
disabled trading for the account and terminal. The EA publishes complete account, position,
overlapping deal-history, visible-instrument, specification, current bid/ask, and broker market-
evidence sections. It contains no order create/check/modify/cancel/close or terminal-state-changing
call. A missing/partial section is an error, never an empty portfolio.

Extend the evidence profile with server-requested visible-symbol batches, multi-window bars/ticks,
`MqlRates.real_volume`, and optional DOM subscription/snapshots through `MarketBookAdd` and
`MarketBookGet`. MT5 bars expose OHLC, spread, tick volume, and broker-supplied real volume; tick
history distinguishes bid/ask activity from last-price/volume changes. Broker DOM is optional and,
for non-exchange Forex, may be absent or limited to broker-client interest, so it is always labelled
`BROKER_PROXY` rather than a global book. See [MqlRates](https://www.mql5.com/en/docs/constants/structures/mqlrates),
[CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange), and
[MT5 market-depth semantics](https://www.mql5.com/en/book/automation/symbols/symbols_market_depth).

**Rationale**: The native outbound EA works in the user's actual macOS/Windows terminal without a
separate Windows Python service, keeps credentials out of TraderX, and makes the prohibited trading
surface statically testable. MT5 remains the only authority for broker support and execution
feasibility while honestly exposing the limits of broker volume/depth.

**Alternatives considered**: The Python `MetaTrader5` IPC bridge, an inbound socket/REST bridge,
Docker/headless MT5, normal trading credentials, arbitrary third-party EAs, and treating missing
DOM/real volume as zero are rejected.

## 24. Provider Selection, Freshness, and Account Authority

**Decision**: V1 supports only `MT5_TERMINAL_BRIDGE` for broker account truth. An
authenticated owner creates/tests an integration, sees only discovered/verified provider accounts,
then binds one account as TraderX's primary live account. The risk service accepts account truth
only from the bound integration after a complete, fresh reconciliation. Configured but unbound,
disabled, degraded, or failed integrations never replace the primary account automatically.

Record provider-specific cursor or overlapping-window checkpoints separately from append-only raw
observations and account snapshots. A checkpoint advances atomically with a normalized complete
snapshot. Any authentication, authorization, TLS/network, rate-limit exhaustion, schema,
identity, cursor/window, or freshness failure triggers an integration-scoped data-quality breaker;
the account remains in `LOCKDOWN` until a subsequent complete reconciliation clears it through the
normal breaker lifecycle. Provider health transitions, connection tests, account selection, binding,
credential rotation, and recovery are auditable high-risk actions.

**Rationale**: TraderX needs one unambiguous source for balance, equity, and positions. A
provider-neutral authority rule prevents a secondary connection, stale cached state, or a partial
reconnect from silently changing portfolio risk.

**Alternatives considered**: accepting the newest provider response without an account binding,
merging simultaneous broker accounts, clearing a breaker on transport recovery alone, storing a
cursor outside the snapshot transaction, and automatic provider failover are rejected.

## 25. Low-Cost Market-Data Catalogue

**Decision**: Ship `MT5_TERMINAL_BRIDGE` as the broker authority for Forex and commodities,
`COINBASE_EXCHANGE` as the cryptocurrency venue authority, and `TWELVE_DATA` as a reviewed
Forex/crypto field-level fallback. CME remains a disabled optional future entitlement, not a V1
gate. An entry is selectable only after the owner supplies a credential where required, passes
connection/capability tests, and approves versioned MT5-to-provider symbol mappings.

- MT5 provides the broker-supported universe, specifications, prices, spread, tick activity,
  execution proxies, and available DOM. All such activity and depth is `BROKER_PROXY`, including
  for broker-supported commodities; it can support an explicitly versioned proxy gate and manual
  recommendation after every other safety gate passes.
- Coinbase REST/WebSocket supplies trades, candles, actual venue volume, and L2/L3 books. WebSocket
  is used for live depth; REST candles are paged and gap-checked. See
  [product candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles),
  [product book](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book),
  and [WebSocket feed](https://docs.cdp.coinbase.com/exchange/websocket-feed/overview).

`TWELVE_DATA` provides Forex and crypto price/candle continuity through `time_series` and latest
prices through documented REST endpoints. Its composite currency feed is aggregated, so every
returned field is `AGGREGATED_PROXY`. Volume is accepted only when the provider supplies it;
Twelve Data has no documented venue-order-book endpoint and cannot supply actual venue volume or
broker-executable liquidity. See [Twelve Data API docs](https://twelvedata.com/docs) and
[composite-feed explanation](https://support.twelvedata.com/en/articles/12528665-how-the-composite-currency-feed-works).

**Rationale**: This supports useful research without a paid CME/Cboe dependency while preserving
the evidence semantics needed for safe decisions.

**Alternatives considered**: treating aggregated data as venue authority, scraping exchange pages,
or claiming global Forex volume are rejected. A paid CME depth entitlement remains a future upgrade.

## 26. Source Authority, Asset-Aware Gates, and Fallback

**Decision**: MT5 is authoritative for broker support/specifications/current execution feasibility;
Coinbase is authoritative only for declared selected-venue crypto capabilities; Twelve Data is never
authoritative. Every measure records provider, venue, mapping, capability,
`ACTUAL`/`BROKER_PROXY`/`AGGREGATED_PROXY`/`UNAVAILABLE`, event/receive time, freshness-policy
version, entitlement, and quality/conflict result.

Forex gates use broker spread, quote/tick activity, freshness, and execution proxies without a
global-book claim. Commodities use official volume/open interest/depth when entitled, otherwise an
explicit versioned MT5 broker-proxy gate; unavailable venue authority remains visible. Crypto uses
Coinbase venue volume/book where available. Twelve Data may replace an exact unavailable Forex or
crypto field only where it supplies that field and the pinned policy permits `AGGREGATED_PROXY`.
Conflicting or unavailable required evidence is `UNKNOWN`, not zero.

After bounded primary attempts, the category tries current complete MT5 evidence, then a fresh
exact Twelve Data field when the policy permits it, then still-fresh cached external evidence. An
outage never extends freshness, fills an unsupported field, or weakens a gate. Otherwise the
category blocks and preserves its active assignment while valid categories may finish.

**Rationale**: Explicit authority and semantics prevent broker proxies, venue data, and missing
values from becoming misleadingly comparable while honoring the requested fallback order.

**Alternatives considered**: provider-last-write-wins, automatic cross-provider merging, zero for
missing evidence, stale-cache grace periods, and failure of all three categories are rejected.

## 27. Durable Coordinated Research Schedule

**Decision**: PostgreSQL owns schedule configuration and occurrence claims; Celery Beat wakes a due
scanner. The schedule stores a repeat interval from one hour through 30 days, anchored local start,
account IANA time zone, enabled state, and next due time. Each unique `(schedule, scheduled_for)`
atomically records either one coordinated parent job with exactly three category children or one
`SKIPPED_OVERLAP` outcome. Leases use fencing tokens; a crash may resume/retry the claimed job but
never create a second occurrence or catch-up run.

Each run pins the approved methodology, source catalogue, freshness/retry policies, and global LLM
selection at start. Independently complete categories may publish selection proposals, but active
assignments change only through separate human approval.

**Rationale**: Database authority survives browser closure, worker restarts, duplicate wakeups,
time-zone transitions, and at-least-once task delivery while providing the exact skip history.

**Alternatives considered**: browser timers, Celery Beat configuration as product truth, queueing
catch-up work, concurrent occurrences, and one independent schedule per category are rejected.

## 28. Reviewed LLM Catalogue and Structured Advisory Port

**Decision**: Implement a provider-neutral server-side port with LiteLLM Gateway as the sole
owner-configurable advisory connection. An owner enters a model alias exposed by that gateway; the
ID is syntax-checked, pinned to future runs, and validated by the gateway adapter at use. LiteLLM
owns upstream provider routing and credentials, while TraderX uses its OpenAI-compatible model and
chat-completions surface. Tools, web/file search, MCP, shell/code execution, and arbitrary
endpoints are disabled.

One global selection applies to all categories. Each invocation records the exact requested and
returned model, catalogue/adapter revision, evidence hash, deterministic method, prompt/schema and
inference-policy versions, attempts, provider request ID, stop/failure reason, token usage, latency,
output hash, and estimated-cost rate-card version. Pinning improves reproducibility but does not
promise bit-for-bit model output; deterministic research remains the authority.

**Rationale**: Fixed reviewed adapters preserve the network and capability boundary while LiteLLM
centralizes owner-approved upstream providers, model aliases, keys, and spend controls without
placing those upstream credentials in TraderX.

**Alternatives considered**: dynamic provider admission from model-list APIs, a generic
OpenAI-compatible endpoint, locally hosted arbitrary models, provider web/tools, category overrides,
and model changes during an active run are rejected.

## 29. LLM Privacy, Retry, and Deterministic Independence

**Decision**: Send only bounded normalized market evidence, evidence identifiers, and deterministic
results. Exclude credentials, MT5/account identity, balance/equity, personal data, raw integration
configuration, unrestricted database content, and untrusted prose instructions. Locally validate
the strict response again; it can contain summaries, anomalies, cautions, data-quality observations,
and methodology proposals but no gate/weight/score/rank/activation/risk/order fields.

TraderX owns at most three attempts, 180 seconds each, within ten minutes overall. Retry classified
timeouts, connection failures, 408/409/429/5xx, and truncation as policy allows; do not retry
authentication/authorization/unsupported-model errors or identical refusals. After exhaustion,
publish the independently valid deterministic report, mark advisory analysis unavailable, alert,
and permit an explicit later retry with the same pinned model. Never substitute a model silently.

Provider retention posture is displayed accurately. OpenAI API data is not used for training by
default but standard abuse monitoring can retain data for up to 30 days; `store=false` is not a ZDR
claim. Anthropic retention depends on workspace/model/contract, and ZDR requires an approved
arrangement. See [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data) and
[Anthropic retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention).

**Rationale**: Data minimization and tool prohibition bound prompt-injection/exfiltration risk;
independent deterministic completion keeps an LLM outage from becoming a market-control outage.

**Alternatives considered**: sending raw pages/account data, hidden SDK retries, unlimited retries,
automatic cross-model failover, failing valid deterministic research, and claiming ZDR from a
request flag are rejected.

## 30. Official Economic Calendar and Guard Windows

**Decision**: Use documented official machine feeds for BLS and BEA schedules, their official APIs
for published values, and EIA API v2 for published petroleum values. Use owner-maintained,
official-URL-cited entries for FOMC and EIA schedules because V1 must not scrape their HTML
calendars. The owner can enable high-impact event types and pre/post buffers; the Risk Manager blocks
new live recommendations for affected active markets inside either buffer. Existing positions,
research, paper trading, and journaling continue.

- BLS publishes an official ICS schedule that includes national-office releases; filter it to CPI,
  PPI, and Employment Situation/NFP. See [BLS schedule](https://www.bls.gov/schedule/news_release/empsit.htm)
  and [BLS developer resources](https://www.bls.gov/developers/home.htm).
- BEA publishes machine-readable schedule formats; use GDP and Personal Income and Outlays/PCE.
  See [BEA calendar](https://www.bea.gov/news/schedule/icalendar) and
  [BEA API guide](https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf).
- EIA published petroleum values use its free API; the owner-cited WPSR schedule records standard
  Wednesday releases and explicit holiday overrides. See [EIA API documentation](https://www.eia.gov/opendata/documentation.php)
  and [WPSR schedule](https://www.eia.gov/petroleum/supply/weekly/schedule.php).
- Owner-cited entries require the official URL, event time, impact, scope, reviewer, reason, and
  audit trail. Machine imports are immutable; a cancellation or correction creates a superseding
  revision. Missing consensus remains `UNKNOWN`, never inferred.

**Rationale**: Separate schedule and release-value imports preserve provenance, avoid scraping, and
turn calendar risk into a deterministic guard rather than LLM judgement. Stale/unverified coverage
inside a relevant guard window fails closed.

**Alternatives considered**: a paid generic calendar, scraping official pages, inferred consensus,
and warning-only event treatment are rejected for V1.

## Resolution Status

All Technical Context questions are resolved. Production enablement remains gated—not ambiguous—on
MT5 investor-mode verification, Coinbase/Twelve Data entitlement and permitted-use rights, reviewed
symbol mappings, official-calendar coverage, and successful LLM provider/model qualification with
the owner's actual account access. Until a gate passes, its catalogue entry stays unavailable and
affected categories fail closed. A paid CME entitlement is optional future work.
