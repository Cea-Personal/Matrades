# Contract compatibility report

Validated on 2026-08-14 against the FastAPI-generated `/api/v1/openapi.json`, the committed
provider port, the domain-event catalog, and the typed web client.

## Compatibility summary

| Surface | Status | Evidence |
|---|---|---|
| Generated FastAPI OpenAPI | PASS | 82 versioned paths and 92 unique operation IDs; contract and negative-capability tests pass |
| Web client to runtime API | PASS | TypeScript, ESLint, component tests, production build, and 19 browser journeys pass |
| MT5 provider port | PASS | Native outbound EA enrollment/snapshot flow, MT5-only registry, and prohibited trade-method guards agree |
| Hand-authored `http-api.yaml` | PARTIAL | 53 paths; 33 are exact runtime matches, with renamed resources and six material design-only operations |
| Domain-event catalog | FAIL | 44 cataloged events, but only three event types are emitted by production source |

The FastAPI-generated schema is authoritative for executable clients until the hand-authored
contract is generated from the same source. This decision does not add any live-order capability.

## HTTP reconciliation

The most important name changes are deliberate and used by the integrated Command Center:

| Hand-authored path | Runtime path |
|---|---|
| `/active-markets` | `/markets/active` |
| `/active-markets/{category}` | `/markets/active/{category}` |
| `/audit-events` | `/operations/audit` |
| `/backtest-runs` | `/validation/backtests` |
| `/instruments` | `/markets/instruments` |
| `/journal` | `/journal/entries` |
| `/journal/{entry_id}/annotations` | `/journal/entries/{entry_id}/annotations` |
| `/market-research-runs` | `/markets/research` |
| `/market-research-runs/{run_id}` | `/markets/research/{run_id}` |
| `/notifications` | `/notifications/inbox` |
| `/paper-runs` | `/paper/runs` |
| `/strategies/{strategy_id}/versions/{version_id}/approval` | `/approvals/strategies/{strategy_version_id}` |
| `/validation-runs` | `/validation/runs` |

The runtime also includes integration enrollment/rotation/lifecycle, journal attachment/analytics,
market reactivation, notification preferences/tests, job SSE/action routes, and operations health
that are absent from the hand-authored YAML.

Material design-contract operations with no equivalent runtime operation remain:

- account detail and account-scoped circuit-breaker collection;
- circuit-breaker acknowledgement;
- a general event feed;
- position monitoring detail distinct from the frozen-thesis endpoint;
- recommendation lookup by recommendation ID.

The generic `/jobs/{job_id}/{action}` design path is represented by the narrower runtime
`/jobs/{job_id}/actions` and `/jobs/{job_id}/cancel` operations.

## Domain-event reconciliation

Production source currently emits:

- `com.traderx.markets.active-assignment-approved.v1`;
- `com.traderx.markets.active-assignment-deactivated.v1`;
- `com.traderx.strategy.version-created.v1`.

The catalog contains 44 event types and names the deactivation fact
`com.traderx.markets.active-assignment-ended.v1`, so the event contract is not yet compatible.
Audit records and durable database state exist for many corresponding mutations, but they are not
substitutes for the promised outbox event contract.

## Release consequence

T245 remains incomplete and production review remains blocked until the HTTP contract has one
authoritative generated source and every release-scoped domain mutation either emits its cataloged
event transactionally or the catalog is deliberately narrowed and versioned. Provider-port safety
is already reconciled and no adapter, API, worker, or UI operation submits, changes, or closes a
real-money order.
