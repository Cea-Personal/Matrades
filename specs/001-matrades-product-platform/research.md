# Phase 0 Research: Matrades Product Platform

**Date**: 2026-08-25
**Status**: Complete — no unresolved technical clarifications

This document consolidates the three supplied plans, the product specification, current primary
documentation, and constitutional constraints. Every decision favors deterministic safety,
reconstructability, and the smallest viable V1 operational footprint.

## 1. Deployment and module topology

**Decision**: Use a monorepo and deploy a Python modular monolith through separate API and worker
processes, a Next.js web process, shared PostgreSQL/Redis infrastructure, and an independent MT5
bridge. Enforce domain boundaries in packages; extract network services only after measured need.

**Rationale**: Risk, policy, reservations, approvals, and reconciliation benefit from transactional
consistency. API and workers need different scaling but can compose the same modules. The bridge must
run where MT5 runs, which is the only necessary early network boundary.

**Alternatives considered**:

- Microservices per domain: rejected for V1 because distributed transactions and operations add risk
  without established load.
- One process: rejected because ingestion, indexing, research, and backtests must not block user APIs.
- Serverless-only functions: rejected because durable streams, long jobs, and MT5 connectivity need
  controlled process lifecycles.

## 2. Runtime baselines

**Decision**: Use Python 3.13 for the backend/workers and TypeScript 5.x on Node.js 24 LTS for the web.
Use Next.js 16 Active LTS and pin all exact dependency versions in lockfiles. Reassess Python 3.14
after the numerical, backtesting, orchestration, and worker dependency matrix is certified.

**Rationale**: Python 3.13 remains in bugfix support and is explicitly supported by the mature Celery
5.5 line; Node 24 is the current LTS baseline, and Next.js 16 is Active LTS. This balances security
support with compatibility for quantitative libraries.

**Alternatives considered**:

- Python 3.14: supported upstream but deferred until all quantitative and workflow packages certify it.
- Node 26: still Current rather than LTS on the planning date.
- Next.js canary: rejected because production must use an LTS release.

## 3. API and real-time transport

**Decision**: Use FastAPI/Pydantic for versioned HTTP/OpenAPI commands and queries. Use SSE for
authenticated server-to-browser operational events and WebSocket only for high-rate provider or MT5
bridge streams. Version all schemas and generate the TypeScript client/types from OpenAPI.

**Rationale**: FastAPI provides standards-based OpenAPI and JSON Schema validation. SSE is simpler
for one-way UI state delivery and reconnects naturally; provider/bridge channels require continuous
bidirectional or high-rate behavior.

**Alternatives considered**:

- GraphQL: rejected because explicit financial command/state contracts and generated audit-friendly
  schemas are a better V1 fit.
- WebSocket for every UI interaction: rejected as unnecessary operational complexity.
- Polling only: rejected because approvals, disconnects, and live monitoring need prompt updates.

## 4. Persistent data architecture

**Decision**: Use PostgreSQL 17 as the V1 system of record, with compatible TimescaleDB and pgvector
extensions. Keep `TimeSeriesStore` and `SemanticIndex` ports so either workload can move later.
Redis is a cache, rate limiter, distributed lock provider, and Celery transport—not an authority.

**Rationale**: PostgreSQL transactions simplify cross-domain invariants. TimescaleDB supports
partitioned time-series operations, while pgvector and PostgreSQL full-text/metadata filters provide
sufficient V1 hybrid retrieval without another database. PostgreSQL 17 is chosen over 18 until the
selected TimescaleDB hosting matrix certifies the newer major; pgvector supports both.

**Alternatives considered**:

- PostgreSQL 18 immediately: current upstream, but extension/hosting compatibility takes priority.
- Dedicated time-series and vector databases: deferred until volume, latency, or isolation evidence
  justifies their operational cost.
- Redis workflow state: rejected because eviction or restart cannot erase approvals or reservations.

## 5. Background and scheduled work

**Decision**: Use Celery 5.6 with Redis transport for ingestion, indexing, research, backtests,
notifications, and scheduled health checks. Every task has an idempotency key, bounded retry policy,
timeout, owner/correlation context, and durable database job record. Tasks acknowledge only after
idempotent state changes commit.

**Rationale**: Celery provides mature task routing, scheduling, retry, monitoring, and worker
scaling. Database job records preserve user-visible truth independently of the queue.

**Alternatives considered**:

- Dramatiq or ARQ: viable but provide less of the selected scheduling/monitoring ecosystem.
- Kafka: rejected for V1; throughput requirements do not justify a second event platform.
- In-process background tasks: insufficient for long-running, restart-safe work.

## 6. Agent orchestration and workflow ownership

**Decision**: Use LangGraph for bounded, checkpointable AI subflows, with per-invocation specialist
state by default. Application-owned database state machines control research, HIL, trading, and
strategy promotion. An agent step cannot perform or skip a domain transition.

**Rationale**: LangGraph persistence supports interrupt/resume and fault tolerance, but the
constitution requires deterministic services and durable application records to own authority.
Keeping these roles separate avoids making framework checkpoints the financial ledger.

**Alternatives considered**:

- Hand-coded agent loops: simpler initially but weaker for resumable multi-step reasoning and audit.
- LangGraph as the sole workflow engine: rejected because HIL, risk, and broker state require explicit
  domain transactions independent of an AI framework.
- Autonomous agent-to-agent delegation: rejected; the Orchestrator invokes fixed roles through contracts.

## 7. Agent runtime, prompts, and tools

**Decision**: Use a Matrades-owned `AgentRuntimeAdapter` with `CODEX_APP_SERVER` as the mandatory
default for every required logical agent. Dedicated agent-worker containers use the stable Python
Codex SDK and its pinned Codex CLI/App Server runtime over local stdio. `LITELLM` is a separately
enabled adapter that an operator must explicitly assign to an agent or model profile; model
fallbacks remain within the selected runtime and no automatic cross-runtime fallback exists.
Matrades continues to own models, runtime-bound profiles, credentials, capability requirements,
agent configuration versions, prompt versions, and tool permission sets. System prompts resolve as
agent override → orchestrator system prompt → platform default, and user prompts resolve independently
through the corresponding chain.

**Rationale**: The official Codex SDK supports embedding Codex in server-side applications and its
Python SDK controls a local App Server over JSON-RPC. Using the supported local stdio path avoids
depending on the App Server's experimental remote WebSocket transport. Resolving runtime before
model, recording the configured and actual runtime, and forbidding silent cross-runtime routing make
the user's Codex-first rule testable and auditable while retaining an explicit LiteLLM escape hatch.
Stable permission sets remain outside both runtimes.

**Alternatives considered**:

- LiteLLM as the default execution gateway: rejected by the clarified product requirement that all
  required agents default to Codex.
- Automatic Codex-to-LiteLLM failover: rejected because it would silently change runtime, provider,
  credential, and audit semantics.
- Remote App Server WebSocket workers: rejected for V1 because official documentation marks that
  transport experimental and unsupported for production workloads; co-located stdio is supported.
- Treating Codex cloud chats as a general application-agent API: rejected because documented cloud
  environments are repository task containers, while the SDK/App Server is the documented product
  integration surface.
- One global model/prompt: rejected because fixed roles require independent tuning.
- Prompt-controlled tools: rejected because prompt changes must never alter authority.

## 8. Provider and adapter strategy

**Decision**: Use capability contracts for model, market, macro, positioning, calendar, news,
broker, embedding, blob, and notification providers. Market connections declare asset classes,
instrument types, venues, history depth, freshness, and supported capabilities such as discovery,
quotes, candles, contract details, futures chains, open interest, funding, corporate actions, and
broker tradability. Routing resolves owner/account → research lane → required capability → explicit
authoritative binding → healthy connection → canonical provider-instrument mapping. V1 retains
Twelve Data, Coinbase, CoinGecko, FRED, CFTC COT, configurable calendar/news providers, and the MT5
bridge, but does not infer that any one provider covers every lane.

For CFDs, the account broker's quote and effective-dated contract terms are authoritative; an
underlying spot or futures feed is reference evidence only. For futures, chain-capable providers may
support discovery and history, but HIL-1 and later stages reference a concrete dated contract.
Priority fallback is permitted only among explicitly configured bindings that preserve the same
asset class, instrument type, venue semantics, and required capability.

**Rationale**: The specification supersedes older plan references to Binance. Central ingestion
prevents inconsistent agent views and enables source substitution without changing business rules.
Capability routing prevents a healthy spot source from being silently treated as an executable CFD
or futures source and makes incomplete matrix coverage visible.

**Alternatives considered**:

- Binance as required V1 feed: rejected because FR-035/FR-036 select Coinbase.
- Direct agent-provider access: rejected because it bypasses normalization, freshness, and permission
  controls.
- CoinGecko for live exchange authority: rejected; its role is broad discovery and metadata.
- One provider per asset class: rejected because capability and legal/execution semantics differ by
  instrument type and venue.
- Automatic cross-type substitution: rejected because it changes ownership, cost, margin, and risk.

## 9. Financial conventions and consistent risk context

**Decision**: Calculate money and quantity using fixed-precision decimal types and explicit units.
Each ruleset defines drawdown basis (`BALANCE`, `EQUITY`, or `HIGH_WATER_EQUITY`), reset timezone,
currency, use of unrealized profit, and severity. Convert currencies using a versioned fresh rate and
round size downward to broker increments. Missing/stale conversion, account mismatch, or an unbounded
position blocks new risk.

**Rationale**: Financial limits cannot be reproduced from binary floating point or ambiguous reset
semantics. Conservative rounding and explicit policy metadata prevent accidental limit breaches.

**Alternatives considered**:

- Floating-point arithmetic: rejected for authoritative finance.
- One universal drawdown convention: rejected because prop programs differ.
- Original account size as capacity: rejected by the specification; current equity governs.

## 10. Reserved risk, concurrency, and dynamic capacity

**Decision**: Treat a position without a valid protective bound as unbounded risk and block new
proposals. Sum remaining Stop Loss loss across open positions. Atomically reserve candidate risk when
an actionable HIL-2 proposal is created; WAIT, REJECT, cancellation, or expiry releases it, TAKE
carries it into awaiting manual entry, and reconciliation replaces it with broker-position risk.
Re-evaluate whenever an input version/freshness status changes.

Dynamic count is computed for a named candidate. Dashboards show remaining risk plus an estimated
count based on a clearly labeled configured standard risk unit; they never present an unconditional
slot entitlement.

**Rationale**: Concurrent proposals can otherwise overcommit the same capacity. Candidate size,
Stop Loss, correlation, and account state determine real capacity, so a raw position count is unsafe.

**Alternatives considered**:

- Reserve only after broker entry: rejected because multiple approved proposals could exceed limits.
- Static concurrent-trade count: retained only as a ceiling.
- Count-only dashboard: rejected because it hides the candidate-risk assumption.

## 11. Portfolio and correlation risk

**Decision**: Combine configurable factor/exposure groups with rolling return-correlation evidence.
Calculate direct, net directional, market-category, and correlated worst-case exposure. The most
conservative applicable configured or statistical limit wins. When correlation evidence is stale or
insufficient, fall back to explicit exposure groups; if no safe grouping exists, block rather than
assume independence.

**Rationale**: Pair names do not describe shared USD, rates, crypto-beta, or cross-market exposure.
Statistical estimates alone can also fail during regime changes.

**Alternatives considered**:

- Static correlation matrix only: too slow to reflect changing regimes.
- Rolling correlation only: too fragile with sparse or unstable data.
- Treat every position independently: prohibited by FR-031.

## 12. Strategy representation and lifecycle

**Decision**: Store family-aware declarative specifications with immutable accepted rule revisions
and provenance. Conversation and suggestions are non-canonical. Canonicalize and hash before
structural/parameter comparison, semantic candidate search, and behavioral comparison. Compile one
versioned evaluator used by backtest, paper, and live setup detection.

Use `DRAFT → SPECIFIED → IMPLEMENTED → BACKTESTING → VALIDATING → PAPER_TRADING → APPROVED →
ACTIVE`; allow `DEGRADED`, `SUSPENDED`, and `RETIRED` after approval. Material improvements branch
from, never mutate, an active version. Exact canonical duplicates cannot create a new identity.

**Rationale**: One origin-neutral pipeline prevents human or AI provenance from becoming a quality
shortcut and prevents backtest/live logic divergence.

**Alternatives considered**:

- Executing generated Python: rejected as unsafe and difficult to audit.
- Separate human/AI pipelines: rejected by equal-validation requirements.
- Semantic similarity alone: rejected because it cannot establish rule identity.

## 13. Knowledge and authoritative retrieval

**Decision**: Use a retrieval router that sends current facts to structured services, time-series
questions to time-series queries, policy/risk to deterministic engines, and contextual questions to
the Knowledge service. Hybrid retrieval combines authorization scope, metadata, full-text, and
vector similarity. Persist source/document/segment/version/embedding provenance and retrieval audit.

Disabling/deleting a source removes it from retrieval and purges authorized content/embeddings while
retaining a minimal immutable tombstone and non-content decision references required for audit.

**Rationale**: Retrieval can improve research without becoming current financial truth. Explicit
routing is more reliable than asking an AI to choose its own source of authority.

**Alternatives considered**:

- Dedicated vector database: deferred; pgvector is sufficient and simpler for V1.
- RAG for policy or performance calculation: rejected by constitution.
- Delete every historical reference: rejected because it would make material decisions irreproducible.

## 14. Security and secret management

**Decision**: Require email verification, TOTP MFA, recovery codes, revocable sessions, least-
privilege scopes, and step-up MFA for sensitive mutations. Use a vault port with envelope encryption;
production master keys reside in an external key manager, never the database. Store ciphertext,
key-version reference, masked suffix, rotation history, and access audit. Use mTLS for remote MT5
bridges and a rotating scoped token on loopback-only installations.

**Rationale**: Database-only encryption keys fail with the database backup; external key custody,
rotation, and scoped retrieval protect every provider and broker credential.

**Alternatives considered**:

- Plain environment variables for all user credentials: rejected because users configure multiple
  rotating credentials through the UI.
- A database encryption key stored beside ciphertext: rejected as ineffective separation.
- Broker write scopes: excluded from V1.

## 15. Contracts, concurrency, and audit

**Decision**: Publish OpenAPI, event, adapter, and agent contracts. Mutating commands require user
authorization, idempotency key, expected aggregate/configuration version, and audit correlation ID.
Events use a versioned envelope and per-aggregate ordering; consumers deduplicate by event ID. Every
material evaluation references immutable input snapshots and exact code, strategy, ruleset,
guardrail, configuration, prompt, provider/model, and tool versions.

**Rationale**: Optimistic concurrency prevents stale UI or worker writes, while idempotency prevents
replayed messages from duplicating approvals, risk reservations, or broker events.

**Alternatives considered**:

- Last-write-wins mutation: rejected for financial and configuration state.
- Unversioned event payloads: rejected because consumers and audit replay must evolve safely.
- Raw agent transcripts as audit: rejected; structured decision evidence is authoritative and avoids
  storing private reasoning.

## 16. Testing and release evidence

**Decision**: Combine unit, property, integration, adapter contract, replay, security, failure, and
browser E2E suites. Property tests enforce monotonic safety: tighter limits or added exposure cannot
increase size/capacity. Replays enforce point-in-time data and one evaluator across backtest, paper,
and live. SC-001 through SC-015 are executable release gates.

**Rationale**: Example tests miss rounding, boundary, concurrency, and time-ordering failures that
cause the most serious trading defects.

**Alternatives considered**:

- E2E-only coverage: rejected because financial edge cases need fast exhaustive tests.
- Unit-only coverage: rejected because provider, persistence, workflow, and browser boundaries fail
  differently in integration.
- Live-provider-only tests: rejected as non-reproducible; use fixtures plus provider sandboxes.

## 17. Operations, retention, and recovery

**Decision**: Keep material trade, approval, policy, risk, strategy, agent execution, and audit
evidence for seven years by default, subject to a stricter applicable rule. Use shorter configurable
tiers for raw high-frequency market data while preserving derived decision snapshots. Encrypt and
test backups; target a 15-minute RPO and four-hour RTO for authoritative V1 data. Every critical
integration has safe-disable, reconnect, and rollback procedures; migrations require forward and
rollback validation before release.

**Rationale**: Long-lived evidence supports performance analysis and reconstructability, while raw
stream retention can be tiered for cost. Explicit recovery targets make durability testable.

**Alternatives considered**:

- Indefinite retention for every raw event: rejected for privacy and cost.
- User-deletable material audit rows: rejected; authorized deletion removes content where allowed but
  retains minimal compliance/audit tombstones.
- Backup without restore tests: rejected because an untested backup is not a recovery control.

## 18. Canonical instrument identity and specification authority

**Decision**: Separate `UnderlyingAsset`, typed `Instrument`, exact `VenueInstrument`, and dated
`FuturesContract` identities. A `ResearchLane` is the stable `(asset_class, instrument_type)` key.
Effective-dated immutable `InstrumentSpecificationVersion` records preserve quantity unit,
multiplier, tick size/value, quote/settlement/margin/P&L currencies, minimum/maximum/increment,
calendar, margin, financing/funding, ownership semantics, expiry/notice/roll fields, source,
freshness, and normalization version. Provider symbols are aliases, never IDs. Broker-issued CFDs
remain distinct across issuers even when they reference the same underlying.

**Rationale**: A symbol such as `XAUUSD` may represent spot metal, a broker CFD, or a synthetic
provider series. A futures root or continuous series is not an executable dated contract. Separate
identities prevent cross-type price, sizing, reconciliation, and replay errors while preserving
shared-underlying exposure aggregation.

**Alternatives considered**:

- Symbol plus type as the identity: rejected because venue, issuer, currency, and expiry still
  collide.
- Provider symbols as canonical IDs: rejected because they create lock-in and ambiguous aliases.
- One sparse record with every optional product field: rejected because impossible combinations
  become difficult to validate.

## 19. Twelve-lane research orchestration and HIL-1

**Decision**: Each scheduled account run creates 12 durable lane results for Forex, metals,
cryptocurrency, and stocks crossed with spot, CFD, and futures. A lane ends in `READY`, `NO_TRADE`,
`NOT_CONFIGURED`, `UNAVAILABLE`, `STALE`, or `BLOCKED`; a healthy lane contains at most one top
candidate. The aggregate becomes `MARKETS_PENDING_APPROVAL` only when required lane policy permits;
otherwise it is visibly `DEGRADED`, while healthy results remain reviewable and unresolved lanes
cannot reach HIL-2. HIL-1 replacement keys include both dimensions and cannot switch types silently.

Add protected `stocks_research` as the fourth asset-class specialist, raising the required registry
to 16. Each asset-class specialist ranks its three types independently; shared technical,
fundamental, sentiment, regime, and critic roles retain cross-asset contracts.

**Rationale**: Twelve independent terminal records prove coverage and isolate failure without
fabricating a result or discarding valid evidence. Candidate IDs, not symbols, prevent score and
approval collisions between wrappers over one underlying.

**Alternatives considered**:

- One result per asset class: rejected because it collapses spot, CFD, and futures.
- Twelve unrelated workflows: rejected because provider source cuts and common evidence should be
  reused.
- Letting the Orchestrator research stocks: rejected because its authority is coordination, not
  specialist market ranking.

## 20. Instrument-aware valuation, sizing, and aggregate exposure

**Decision**: Dispatch deterministic valuation by instrument type using fixed-precision decimals
and explicit units. Spot exposure uses native quantity and cash/underlying availability; CFD P&L
uses broker quantity, contract multiplier, price movement, financing, and cash adjustments; futures
P&L uses exact contract count, tick movement, and tick value. Notional, required margin, and maximum
loss remain distinct.

Sizing calculates loss per minimum quantity increment from entry to Stop Loss, adds spread,
commission, slippage/gap allowance, financing where applicable, and currency conversion, divides the
permitted risk budget, rounds down, and recalculates risk, margin, portfolio, category, and correlated
exposure. Missing or stale loss-critical terms hard-block HIL-2. Exposure groups aggregate the same
underlying across spot, CFD, and futures.

**Rationale**: One share, one coin, one CFD lot, and one futures contract do not represent the same
quantity or loss. Margin is collateral, not a loss bound, and wrapper diversity is not economic
diversification.

**Alternatives considered**:

- A universal lot unit: rejected as ambiguous and unsafe.
- Nearest-increment rounding: rejected because it can exceed the risk budget.
- Free margin as risk capacity: rejected because it does not bound loss.

## 21. Futures, corporate actions, financing, and deterministic replay

**Decision**: Rank and approve exact executable futures contracts selected from a point-in-time
chain using configured liquidity, open-interest, first-notice, last-trade, and roll rules.
Continuous/back-adjusted series may generate analytical signals but are never tradable identities;
rolls are explicit new decisions and transactions. Persist stock splits, dividends, rights, mergers,
symbol changes, spinoffs, suspensions, and delistings as point-in-time corporate actions. Persist CFD
financing and broker cash-adjustment terms as effective-dated observations.

Backtest, paper, and live evaluation pin the executable listing, specification version, universe
membership, raw data cut, calendar, FX cut, cost/financing/funding model, corporate-action treatment,
futures chain and roll rule, rounding order, evaluator/code version, and random seed. Stock tests
retain delisted constituents; CFD profiles cannot pass validation without reliable historical terms.

**Rationale**: Silent rolls, retrospective adjusted fills, omitted financing, and survivorship bias
make results irreproducible and overstate performance.

**Alternatives considered**:

- Trade a continuous futures symbol: rejected because it is synthetic.
- Use adjusted stock prices as historical fills: rejected because the adjustment was not executable.
- Reuse spot validation for CFDs/futures: rejected because costs and lifecycle differ materially.

## 22. Shared source cuts, quotas, and account-specific filtering

**Decision**: Preserve each trading account's schedule, but resolve its lane manifest into shared
provider source-cut jobs. Deduplicate requests by connection, provider instrument, capability,
timeframe, and cutoff; then apply account-specific broker tradability, policy, and risk filtering.
Use per-connection token buckets, endpoint cost weights, batching, `Retry-After`, bounded retries,
and circuit breakers. Health probes remain separate from research symbol calls.

**Rationale**: Running the same provider fetch independently for every account wastes quota and can
produce inconsistent evidence cuts, while one global final ranking would ignore account-specific
tradability and policy.

**Alternatives considered**:

- Full provider run per account: rejected because it duplicates calls.
- One global schedule and ranking: rejected because account schedules and eligibility differ.
- Cache final candidates only: rejected because account filters and decision evidence must remain
  reproducible.

## 23. Migration from category-only instrument records

**Decision**: Use an expand/compatibility/contract migration. Preserve existing category-only
research, selection, proposal, and trade records as immutable `LEGACY_UNTYPED` evidence. Add typed
lane, venue-listing, specification-version, and dated-contract references without guessing values;
backfill only mappings proven by historical broker/provider evidence. Dual-read during the migration,
require typed references for all new actionable writes, regenerate clients together, and retire the
legacy write shape only after every worker and UI consumer supports the new contract.

**Rationale**: A legacy `XAUUSD` or similar symbol cannot prove whether the original semantics were
spot, a broker-issued CFD, or a provider's analytical series. Guessing would corrupt audit history
and could cause unsafe reuse, while deleting it would break reconstructability.

**Alternatives considered**:

- Infer type from symbol: rejected because symbols are provider-specific aliases.
- Rewrite historical records in place: rejected because it destroys the original evidence shape.
- Big-bang destructive migration: rejected because mixed worker/UI versions and rollback would be
  unsafe.

## Primary Sources

- [Python version support](https://devguide.python.org/versions/)
- [Node.js release status](https://nodejs.org/en/about/previous-releases)
- [Next.js support policy](https://nextjs.org/support-policy)
- [FastAPI standards and validation](https://fastapi.tiangolo.com/features/)
- [PostgreSQL current documentation](https://www.postgresql.org/docs/current/)
- [Timescale PostgreSQL extension model](https://docs.timescale.com/use-timescale/latest/extensions/)
- [pgvector PostgreSQL support](https://github.com/pgvector/pgvector)
- [Celery stable documentation](https://docs.celeryq.dev/en/stable/)
- [LangGraph persistence and HIL](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Codex cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment)
- [Twelve Data API documentation](https://twelvedata.com/docs/introduction/quickstart)
- [Coinbase Advanced Trade product contract](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/get-product)
- [MQL5 symbol and contract properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)
- [IBKR contract definitions](https://interactivebrokers.github.io/tws-api/basic_contracts.html)
