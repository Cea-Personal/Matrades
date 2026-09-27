# Code-quality cleanup — 2026-09-27

## Scope and safeguards

Repository-wide file/reference inventory, Python AST duplicate scans, lint and type checks,
and targeted inspection covered the frontend, API, workers, domain modules, adapters,
shared persistence, MT5 bridge/runtime, tests, and deployment entry points. This is a
conservative cleanup, not a claim that every line or external integration is defect-free.

Existing working-tree edits were preserved. Native agent models/reasoning, environment
secrets, account records, execution permissions, provider bindings, dependencies, database
schemas, strategy parameters, and risk calculations were not changed. No live research,
provider probes, broker orders, migrations, deployment, or container restart was performed.

## Resolved findings

- **Duplicated agent configuration resolution:** the API and isolated worker now share
  `modules/agents/configuration.py`. Native defaults are still loaded afresh; saved profiles
  remain owner-scoped overrides with the same stable IDs and source annotations.
- **Duplicated row-action concurrency bookkeeping:** agent and connection tests share
  `useKeyedMutation`. Synchronous duplicate-click protection, concurrent different-row
  tests, asynchronous success handling, per-row errors, and explicit agent bulk testing
  retain their behavior. Automatic test retries remain disabled.
- **Repeated agent test payloads and test helpers:** single and bulk agent checks use one
  request builder. Controlled-promise fixtures share one helper.
- **Duplicate broker command protocols:** the execution service imports the existing
  `BrokerCommandPort`; the former import location continues to expose the same name.
- **Duplicate Trade Plan read handlers:** both `/trade-plans` and
  `/automation/trade-plans` URL families remain available and share owner-scoped handlers.
- **Redundant transaction rollback:** the shared unit of work relies on SQLAlchemy's
  transaction context. Regression tests cover commit, exception rollback, cancellation
  rollback, and preservation of the original exception.
- **Unused UI scaffolding:** `TradeProposalPanel`, `SimilarityReview`, and
  `ValidationResults` had no application imports. They were removed; tracked versions
  remain recoverable from Git. No account or research data was deleted. Existing source
  checks now reference the actual trading/strategy screens, with additional rendered
  behavior tests. Historical completed-task references are intentionally retained.
- **Broken non-JSON API error handling:** the frontend reads failed response bodies once,
  retaining JSON detail/message fields or a text fallback. Regression coverage also
  verifies cookies, explicit/stored step-up grants, multipart requests, empty success
  responses, and failed MFA preventing sensitive actions.
- **Blocking local MT5 startup/status operations:** filesystem and process inspection and
  launch run off the asynchronous event loop; the synchronous status endpoint runs in
  FastAPI's thread pool. Concurrent startup requests still launch at most one terminal,
  and an already-running user terminal is not relaunched.
- **Type ambiguity and shadowed variables:** explicit Decimal/enum conversions, typed
  research helpers, distinct provider clients, and explicit checks of required instrument
  identity preserve successful-path output. Missing import records and impossible native
  replay state fail explicitly instead of proceeding with incomplete state.
- **Stale tests/documentation:** removed obsolete UI-file and label assumptions, made the
  MT5 authority fixture independent of local secrets, and made reasoning assertions follow
  native configuration instead of a hard-coded `medium`. Architecture documentation no
  longer claims obsolete model assignments, mandatory trade approvals, or verified model
  evidence without runtime proof.

## Verification

| Check | Before cleanup | After cleanup |
| --- | --- | --- |
| Python tests | 469 passed, 7 failed | 492 passed, 1 existing failure |
| Frontend unit/component tests | 56 passed | 73 passed |
| Python lint | 11 findings | Passed |
| Python type checking | 89 errors | Passed across 335 source files |
| Frontend lint and TypeScript | Passed | Passed |
| Playwright browser regressions | — | 16 passed |
| Frontend production build | — | Passed |
| Checked-in contract version guard | — | Passed |

The contract script verifies its documented lightweight artifact/version guard, not full
OpenAPI regeneration. Python tests under `tests/e2e` are source-level smoke checks;
Playwright is the actual browser suite. Browser/API/provider tests use isolated data and
mocks; these checks do not establish real broker connectivity or production profitability.

Two narrowly scoped `type: ignore[misc]` annotations identify untyped native Cython base
classes in NautilusTrader. Application replay state is explicitly typed/checked; no global
lint/type suppression or relaxed trading gate was introduced. Narrow lint exceptions also
document the MT5 wrapper's allow-listed non-secret status file and configured, resolved
process binaries invoked without a shell. Native replay tests cover ordinary, trailing,
break-even, and combined protection management.

## Unresolved deployment finding

`tests/security/test_mt5_desktop_gateway.py::test_vnc_and_bridge_listen_only_on_loopback`
still fails. The current root `start.sh` initializes and diagnoses Wine, then sleeps to
keep the container alive. It does not launch nginx, the bridge, x11vnc, or websockify, so
it cannot satisfy the documented desktop-gateway startup contract. The failure existed
before this cleanup. The gateway template's authentication check still passes.

Restoring a deployable desktop startup script is a functional deployment change, not a
behavior-preserving deletion/refactor. Neither the script nor its security requirement
was changed or skipped. The MT5 README's gateway instructions should not be treated as
proof that the current diagnostic script supplies those services.

## Deliberately retained

Independent Dockerfiles retain shared dependency-install prefixes so each can build with
its existing service context and cache layers. Explicit authorization checks at separate
API/domain/broker boundaries are defense in depth, not accidental duplication. Provider
fallbacks, compatibility routes, deterministic research baselines, and Pydantic defaults
were not removed merely for looking repetitive. No optional research provider was added.
