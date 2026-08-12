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

- the generated web client compiles against [http-api.yaml](contracts/http-api.yaml);
- every HTTP operation has a unique operation ID and versioned path;
- event and provider-port fixtures validate;
- no broker adapter or API operation exposes live order create/change/cancel/close;
- secret fields are write-only or masked and problem responses follow the documented shape.

## 2. Start the Local Validation Environment

```bash
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d postgres redis
docker compose -f deploy/compose.yaml run --rm migrate
docker compose -f deploy/compose.yaml up -d web api worker-monitoring worker-data worker-research worker-notifications scheduler
docker compose -f deploy/compose.yaml ps
```

Expected outcomes:

- only the HTTPS development entry point is exposed outside the private network;
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

1. Connect a fixture broker through the UI with a write-only secret.
2. Test, disable, reconnect, and rotate the credential.
3. Ingest canonical account, instrument, quote, candle, position, and deal fixtures.
4. Replay duplicates, out-of-order observations, a partial fill, a stream gap, and a contradictory
   authoritative snapshot.
5. Advance the fixture clock beyond the freshness policy and restore it with reconciliation.

Expected outcomes:

- secrets are masked and absent from application, worker, telemetry, and audit logs;
- duplicates do not duplicate positions, trades, alerts, or risk;
- partial fills remain distinct and out-of-order input does not regress projections;
- contradiction/gap/staleness degrades the integration, trips the applicable safety condition, and
  blocks new recommendations;
- fresh authoritative reconciliation clears the data block only through the configured breaker
  lifecycle, retaining all history.

## 6. Validate Market Selection

Seed each category with:

- a volatile but illiquid candidate;
- a deeply liquid candidate with high usable volatility;
- a candidate with missing tick value or unusable minimum volume; and
- a prop-restricted candidate.

Run market-universe research from the UI and inspect the report.

Expected outcomes:

- data, liquidity, execution, broker, prop, and sizing gates run before final ranking;
- each ineligible candidate shows its evidence and cannot be approved;
- the report preserves metrics, weights, methodology, dataset manifests, rank, and explanation;
- the user may approve at most one eligible Commodity, Forex pair, and Cryptocurrency pair;
- a later higher score recommends review but never silently replaces the current assignment.

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
uv run pytest tests/integration/test_outbox_redelivery.py
uv run pytest tests/integration/test_worker_crash_recovery.py
uv run pytest tests/integration/test_backup_restore.py
uv run pytest tests/e2e/test_browser_closed_jobs_continue.py
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
