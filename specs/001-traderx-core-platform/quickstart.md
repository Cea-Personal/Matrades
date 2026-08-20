# TraderX Core Platform Validation Quickstart

This guide defines the runnable validation path the implementation must satisfy. It is a design-
phase acceptance guide, so the commands become available as the milestones in [plan.md](plan.md)
are implemented. Detailed records and transitions are defined in [data-model.md](data-model.md);
interfaces are defined under [contracts/](contracts/).

## Prerequisites

- Linux, macOS, or a compatible development container
- Docker with Compose support
- Node.js 24 LTS and the repository-selected package manager
- Python 3.13 and `uv`
- No real-money trading credentials; use contract fixtures, sandbox/demo accounts, or read-only
  test credentials only
- For broker-adapter validation: a dedicated MT5 **demo** account using an investor/read-only
  password. The password is entered only into the local MT5 terminal, never into TraderX.
- Recorded or synthetic fixtures for MT5, Coinbase Exchange, Twelve Data, official calendar feeds,
  and owner-cited calendar entries; production entitlements and redistribution rights are not
  required for local tests.
- A test OpenAI or Anthropic API project/model credential, or the contract test adapter. Never use
  prompts containing account identity, equity, personal data, or integration secrets.
- A test MFA authenticator and optional test Email/Telegram destinations

Never place production secrets in shell history, repository files, fixtures, screenshots, or test
logs. The quickstart MUST NOT require a live-order-capable credential.

## 1. Verify Contracts and Static Quality

```bash
npm --prefix apps/web install
uv sync --all-groups
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
uv run ruff check .
uv run mypy src apps/api apps/worker
uv run pytest tests/contract
```

Expected outcomes:

- the design contract in [http-api.yaml](contracts/http-api.yaml) reconciles with the FastAPI-
  generated runtime OpenAPI before client generation;
- every HTTP operation has a unique operation ID and versioned path;
- event and provider-port fixtures validate;
- no broker adapter or API operation exposes live order create/change/cancel/close;
- secret fields are write-only or masked and problem responses follow the documented shape.

## 2. Start the Local Validation Environment

```bash
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d postgres redis
docker compose -f deploy/compose.yaml run --rm migrate
docker compose -f deploy/compose.yaml up -d web api worker-monitoring worker-research worker-notifications scheduler
docker compose -f deploy/compose.yaml ps
```

Expected outcomes:

- only the HTTPS development entry point publishes a host port;
- only `worker-research` joins the outbound `provider-egress` network so reviewed fixed provider
  endpoints such as Coinbase Exchange can be qualified and queried;
- PostgreSQL and Redis report healthy;
- the API, workers, scheduler, and outbox dispatcher report ready;
- `/api/v1/health` reveals liveness without sensitive configuration;
- restarting the browser or web process does not stop jobs or monitoring.

## 3. Run Automated Test Gates

```bash
uv run pytest tests/unit tests/integration tests/data_quality
uv run pytest tests/reproducibility
uv run pytest tests/security
uv run pytest tests/safety
npm --prefix apps/web test
npm --prefix apps/web run test:e2e
```

The safety suite is release-blocking and MUST exercise the gates in the plan. Integration tests
use real disposable PostgreSQL/Redis/worker processes; eager worker mode alone is insufficient.

## 4. Validate Identity and the Safe Control Plane

1. Open `/setup` as an unauthenticated visitor and create the initial owner through the one-time
   setup flow. Attempt a concurrent second setup and confirm it fails without creating another user.
2. Enroll TOTP at `/mfa/enroll`, save the displayed recovery codes, and confirm the Command Center
   is unavailable until the enrollment code succeeds.
3. Sign out, use `/sign-in` and `/mfa/verify`, then confirm an MFA-assured session opens the
   Command Center while a password-only session does not.
4. Use a recovery code at `/mfa-recovery`; confirm it cannot be reused, all prior sessions are
   revoked, and fresh TOTP enrollment is required. As an `OWNER` or `ADMIN` with recent MFA,
   initiate an assisted reset and confirm the same behavior for the target user.
5. Request a password reset at `/password-reset`; test unknown email, used/expired token, and a
   valid token with only TOTP or recovery-code proof. Confirm reset-token possession alone cannot
   reach an operational route and a completed reset revokes every prior session.
6. Advance the test clock beyond 30 inactive minutes and beyond 12 total hours. Confirm each
   request is rejected before mutation and returns the user to sign-in with an expiry explanation.
7. Create one test live account and configure a prop profile and stricter internal policy.
8. Review the Command Center and audit history.
9. Attempt the same risk change as `VIEWER`, then retry a permitted high-risk change with a stale
   entity version and with a repeated idempotency key carrying different content.

Expected outcomes:

- unauthenticated, password-only, expired, and unauthorized access is denied and audited;
- setup permits exactly one initial owner; TOTP and recovery-code reuse fails; reset/recovery and
  assisted reset revoke the required sessions; and sensitive commands require recent assurance;
- each deep-linkable authentication screen exposes only its valid state, provides an accessible
  error/status message, and never exposes operational content before MFA succeeds;
- internal limits win over looser external limits;
- stale commands fail without mutation, identical retries return the original result, and a key
  reused for different content is rejected;
- account, audit, and outbox changes are atomic.

## 5. Validate Integrations and Fail-Closed Data

### MetaTrader 5 native EA bridge

1. In the authenticated Command Center enter the MT5 account login and broker server, then choose
   **Create MT5 setup code**. Download and compile the TraderX Read-only Bridge EA in that MT5
   terminal; neither a bridge URL nor a bridge identity is supplied by the user.
2. Sign in to the intended demo account using its investor/read-only password. In MT5 allow the
   TraderX HTTPS origin under **Tools → Options → Expert Advisors**, attach the EA to a chart, and
   leave Auto Trading disabled.
3. The EA must prove terminal connectivity, exact login/server, and disabled trading at both the
   account and terminal before it sends a snapshot. Run **Test & discover accounts**, bind the
   returned account, then verify that the Command Center records balance, equity, positions, deal
   history, instruments, source/observation time, and terminal version.
4. Replay terminal disconnect, stale response, account/server mismatch, trading-enabled flag,
   duplicate deal, and partial response. None may be interpreted as an empty portfolio. Static
   safety tests must reject `OrderSend`, `OrderCheck`, `SymbolSelect`, and every order endpoint.

### Reviewed market-data and LLM integrations

1. In the existing Integrations panel confirm the fixed catalogue lists MT5 broker evidence,
   Coinbase Exchange for cryptocurrency venue evidence, Twelve Data for Forex/crypto aggregate
   fallback, the official calendar sources, and the reviewed LiteLLM gateway. Attempt to enter an
   arbitrary URL/provider/model and confirm rejection.
2. Connect each fixture adapter through the UI, test it, rotate a write-only test credential,
   disable/re-enable it, and remove it. Confirm secrets never return and capability, venue,
   entitlement, retention, health, and freshness remain visible.
3. Map fixture venue instruments to MT5 broker symbols. Include one externally covered symbol that
   MT5 does not support and one ambiguous CFD-to-benchmark mapping.
4. Replay provider rate limits, entitlement loss, source conflict, missing depth, missing real
   volume, and a retired catalogue/model entry.

Expected outcomes:

- only reviewed entries can become healthy integrations;
- external coverage never makes an MT5-unsupported/ambiguous symbol eligible;
- each observation identifies provider, venue, capability and
  `ACTUAL`/`BROKER_PROXY`/`AGGREGATED_PROXY`/`UNAVAILABLE` semantics; and
- unavailable evidence remains unknown rather than becoming numeric zero.

### Shared fail-closed behavior

1. Test, reconnect, and renew the MT5 enrollment code.
2. Ingest canonical account, instrument, quote, candle, position, and deal fixtures.
3. Replay duplicates, out-of-order observations, a partial fill, a reconciliation gap, and a
   contradictory authoritative snapshot.
4. Advance the fixture clock beyond the freshness policy and restore it with a complete
   reconciliation.

Expected outcomes:

- secrets are masked and absent from application, worker, telemetry, and audit logs;
- duplicates do not duplicate positions, trades, alerts, or risk;
- partial fills remain distinct and out-of-order input does not regress projections;
- contradiction/gap/staleness degrades the integration, trips the applicable safety condition, and
  blocks new recommendations;
- fresh authoritative reconciliation clears the data block only through the configured breaker
  lifecycle, retaining all history.
- MT5 account truth is accepted only from the enrolled native EA when its terminal and account are
  connected, identity-matched, trading-disabled, complete, and fresh. A central Docker service
  does not communicate directly with an MT5 terminal.

## 6. Validate Market Selection

Seed each category with:

- a volatile but illiquid candidate;
- a deeply liquid candidate with high usable volatility;
- a candidate with missing tick value or unusable minimum volume; and
- a prop-restricted candidate.

Run market-universe research from the UI and inspect the report.

Expected outcomes:

- data, liquidity, execution, broker, prop, and sizing gates run before final ranking;
- Forex uses broker spread/tick/execution evidence without claiming a global book; Commodity uses
  official traded volume/open interest/depth when entitled, otherwise an explicitly labelled MT5
  broker-proxy gate; Crypto uses Coinbase venue volume and book depth;
- each ineligible candidate shows its evidence and cannot be approved;
- the report preserves metrics, weights, methodology, source/fallback manifests, actual/proxy
  semantics, rank, deterministic explanation, and optional advisory analysis;
- the user may approve at most one eligible Commodity, Forex pair, and Cryptocurrency pair;
- a later higher score recommends review but never silently replaces the current assignment.

### Ordered source fallback

1. For one category exhaust the specialist adapter's bounded retries.
2. Supply current complete MT5 evidence and verify it is attempted first.
3. Make MT5 insufficient, then supply a previously successful external dataset inside its original
   freshness policy; repeat after advancing beyond that limit.
4. Keep the other two categories independently valid.

Expected outcomes: the trail is primary retries → MT5 → policy-permitted fresh exact Twelve Data
field → fresh cached external → blocked. Twelve Data cannot fill unsupported fields or appear as
venue authority. Stale cache is rejected without extending freshness; the affected active assignment
is unchanged while the two valid categories may complete.

### Economic calendar and event-risk guard

1. Synchronize BLS and BEA fixture schedules and official released-value fixtures. Add an
   owner-cited FOMC or EIA schedule entry with its official URL, impact, affected scope, and reason.
2. Configure a high-impact pre/post-event buffer for the test account, then move the fixture clock
   into its pre-event and post-event windows.
3. Attempt a new recommendation for an affected market, then repeat for an unaffected market and an
   existing open position. Mark required calendar coverage stale inside a guard window.

Expected outcomes: affected new recommendations are blocked with source citation and remaining
buffer; research and monitoring continue; official machine events are not edited in place; manual
entries are audited; stale required coverage fails closed; and no connector extracts calendar HTML.

### Schedule and global model

1. Select one healthy approved LLM model, configure an anchored repeat interval/time zone, enable
   the schedule, close the browser, and advance the fixture clock to the due time.
2. Keep the coordinated job running across the next due time. Restart the scheduler/worker and
   replay the same wake-up.
3. Change the global model while a run is active, then start a later run.
4. Inject conflicting analysis, invalid JSON/schema, refusal, rate limit, timeout, authentication
   failure, and provider outage. Exhaust retries, then request an explicit analysis retry.

Expected outcomes:

- one due time creates exactly one durable coordinated parent job or one durable overlap skip,
  with no concurrent/catch-up run even after duplicate wakeups;
- each parent contains exactly one Commodity, Forex, and Crypto result;
- the active run retains its pinned model and the later run uses the new global selection;
- every invocation records provider/model/catalogue/prompt/schema/inference versions;
- deterministic gates, metrics, scores, ranks, and selection proposals are byte-identical across
  all injected LLM outcomes;
- exhausted analysis is visibly unavailable and alerts the owner without changing models; and
- explicit retry uses the same pinned model and never changes the deterministic report.

## 7. Validate Strategy Evidence and Reproducibility

1. Build a deterministic strategy through the visual editor.
2. Run a historical test with recorded costs, fills, risk, data split, and seed.
3. Run unseen-data, walk-forward, parameter-stability, Monte Carlo, and portfolio validation.
4. Repeat the run with the identical manifest; then change one strategy rule.
5. Feed a profitable but fragile result and a profitable but shared-account-unsafe result.

Expected outcomes:

- identical manifests reproduce signals, trades, metrics, and risk decisions;
- reports show all required metrics and evidence hashes;
- fragile/unsafe candidates cannot progress;
- editing creates a child immutable version while the old version and evidence remain unchanged;
- invalid lifecycle transitions are rejected with unmet prerequisites.

## 8. Validate Paper Trading and Approval

1. Start paper trading for a historically qualified strategy.
2. Verify use of current data, the same strategy interpreter, exact sizing, and current risk rules.
3. Test calendar-duration success without trade-count/regime evidence and vice versa.
4. Inject material paper-versus-history divergence.
5. Complete all evidence gates and attempt approval as `VIEWER`, with stale evidence, without MFA,
   and finally as an authorized recently authenticated owner.

Expected outcomes:

- no single duration/trade-count gate promotes the strategy;
- divergence sends the version to review/research/failure;
- success ends at `AWAITING_APPROVAL`;
- only a current, authorized, deliberate, audited decision creates `LIVE_APPROVED`;
- no real-money order is created during any step.

## 9. Validate Opportunities and Portfolio Risk

Use fixture opportunities with scores from low to 100 and account scenarios containing zero, one,
and two existing live positions.

Expected outcomes:

- opportunity score and risk decision are displayed separately;
- a high score is blocked when safety says no;
- the second recommendation is passed, reduced, or blocked using combined risk and correlation;
- every third position is blocked regardless of score;
- floating/realized loss can reduce capacity `2 -> 1 -> 0` but never raises recovery risk;
- missing equity, stale quote, missing contract detail, or failed risk evaluation returns no
  actionable recommendation;
- every passing recommendation includes complete levels, exact risk/size, reasons, invalidation,
  and expiry, and becomes non-actionable when expired.

## 10. Validate Manual Execution, Monitoring, and Journal

1. Manually introduce a matching fixture broker position for an actionable recommendation.
2. Introduce an unmatched discretionary position and correct its classification.
3. Change market evidence through healthy, watch, weakening, and invalidated conditions.
4. Suspend the strategy while its position remains open, close both positions, and annotate their
   journals with behavioral notes and protected attachments.

Expected outcomes:

- TraderX detects positions but never submits or changes real orders;
- every live position affects shared risk immediately;
- the original thesis is frozen and monitoring only appends observations;
- suspension prevents new signals while existing monitoring continues;
- journal records contain execution, classification, strategy/risk/thesis context, P&L, and R;
- journal analysis may propose research but never modifies a strategy.

## 11. Validate Reactivation and Knowledge Retention

1. Replace an active market that has data, research, strategies, tests, trades, and journals.
2. Verify all records remain accessible in the Instrument Library.
3. Reactivate it after advancing the fixture clock and introducing a data gap.

Expected outcomes:

- replacement physically deletes nothing;
- reactivation identifies reusable evidence, synchronizes only missing data where possible, and
  classifies strategy evidence staleness;
- stale live approval does not resume; required revalidation and human approval run again.

## 12. Validate Resilience and Recovery

```bash
uv run pytest tests/integration/test_transactional_outbox.py
uv run pytest tests/integration/test_job_runtime.py tests/integration/test_job_operations.py
uv run pytest tests/integration/test_backup_restore.py
npm --prefix apps/web run test:e2e -- system_operations.spec.ts
```

Expected outcomes:

- a database commit cannot lose its audit/outbox facts;
- redelivered events and tasks do not repeat financial effects;
- pause/cancel occurs only at safe checkpoints and hard termination is not a user action;
- transient retries are bounded while deterministic failures are not retried;
- restored backups retain evidence, audit, job state, active assignments, and breaker history;
- notification failure never reverses a safety transition and remains visible for retry.

## Completion Evidence

Archive the contract/static reports, automated-test results, golden reproducibility manifests,
market-selection reports, risk traces, authorization matrix, broker reconciliation log, migration
and restore report, and an end-to-end screen recording as release evidence. The release is not
eligible for production until every constitutional and safety gate passes.
