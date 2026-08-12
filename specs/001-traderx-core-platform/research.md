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

## Resolution Status

All Technical Context unknowns are resolved. The decisions introduce no constitutional exception.
