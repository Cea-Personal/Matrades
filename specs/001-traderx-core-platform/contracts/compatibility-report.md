# Contract compatibility report

Validated on 2026-08-20 against the FastAPI-generated runtime OpenAPI, the committed provider
ports/catalogue, the market-research domain-event catalogue, and the typed web boundary.

## Compatibility summary

| Surface | Status | Evidence |
|---|---|---|
| Generated FastAPI OpenAPI | PASS | 89 paths, 102 operations, and 102 unique operation IDs; authentication and negative-capability tests pass |
| Market-research HTTP amendment | PASS | Runtime exposes schedule, model configuration, coordinated start/history/report, category retry, owner-approved mapping, provider catalogue, and non-broker lifecycle routes at the documented `/api/v1` paths |
| Typed web boundary | PASS | Generated schedule/model/source/coordinated schemas compile under strict TypeScript; Vitest, ESLint, and production build pass |
| Provider ports/catalogue | PARTIAL | Runtime now registers Twelve Data as an `AGGREGATED_PROXY`, retires Cboe from new connections, marks CME optional, and preserves MT5/Coinbase roles; full provider lifecycle/browser coverage remains open |
| Economic calendar/event-risk amendment | PARTIAL | Runtime now persists calendar/event-risk evidence, exposes authenticated calendar/policy routes, schedules documented BLS/BEA ICS sync, supports cited owner entries, and applies deterministic new-recommendation blocks; released-value/EIA and full browser/contract coverage remain open |
| Market-research events | PASS | Schedule, occurrence/overlap, coordinated completion, category block, fallback, model change, analysis completion/unavailability/retry use the catalogued event names and transactional outbox |
| Full hand-authored HTTP catalogue | PARTIAL | 64 design paths/70 operations remain broader and use several legacy resource names; runtime OpenAPI remains authoritative for executable clients |
| Full domain-event catalogue | PARTIAL | Amendment facts are implemented, but many pre-amendment catalog entries still have durable state/audit without a corresponding outbox fact |

This reconciliation adds no order operation. Runtime and design contracts both describe manual
trading decision support only.

## Amendment HTTP mapping

The implemented market-research resources match the design server prefix `/api/v1`:

| Operation | Runtime path |
|---|---|
| Schedule read/update | `/api/v1/markets/research/schedule` |
| Global future-run model read/update | `/api/v1/markets/research/model-configuration` |
| Coordinated three-category start | `/api/v1/markets/research/coordinated` |
| Coordinated run history | `/api/v1/markets/research/coordinated` |
| Coordinated evidence report | `/api/v1/markets/research/coordinated/{run_id}` |
| Same-pin advisory retry | `/api/v1/markets/research/category-runs/{run_id}/llm-analysis/retry` |
| Owner-approved specialist symbol mapping | `/api/v1/markets/instruments/{instrument_id}/mapping` |
| Reviewed provider catalogue | `/api/v1/integrations/providers` |
| Non-broker list/create | `/api/v1/integrations/non-broker` |
| Credential rotation | `/api/v1/integrations/{integration_id}/credentials/rotate` |
| Qualification test | `/api/v1/integrations/{integration_id}/test` |
| Entitlement declaration | `/api/v1/integrations/{integration_id}/entitlement` |
| Enable/disable/reconnect | `/api/v1/integrations/{integration_id}/non-broker/state` |
| Remove and revoke | `/api/v1/integrations/{integration_id}` |

All mutations are session-authenticated; schedule/model/coordinated/retry commands enforce an
MFA-assured owner, ETags where a mutable singleton/resource exists, idempotency keys, reasons,
audit evidence, and secret-free responses. Provider creation is catalogue-bound and rejects extra
configuration fields, arbitrary URLs, extra capabilities, or non-allowlisted models. Create,
qualification, credential rotation, entitlement, lifecycle, and removal commands replay the same
completed response for the same request/key and reject conflicting key reuse.

## Runtime/design naming differences retained

The integrated Command Center already uses these established runtime names:

| Hand-authored legacy path | Runtime path |
|---|---|
| `/active-markets` | `/markets/active` |
| `/active-markets/{category}` | `/markets/active/{category}` |
| `/audit-events` | `/operations/audit` |
| `/backtest-runs` | `/validation/backtests` |
| `/instruments` | `/markets/instruments` |
| `/journal` | `/journal/entries` |
| `/market-research-runs` | `/markets/research` |
| `/notifications` | `/notifications/inbox` |

The runtime additionally contains native MT5 enrollment/snapshot, account sync, integration
rotation/lifecycle, journal attachment/analytics, reactivation, preferences/tests, job SSE/action,
and operations-health routes. These differences are documented rather than hidden by an unsafe
second compatibility surface.

## Amendment event reconciliation

`src/traderx/market_research/events.py` binds runtime writes to the catalogue names:

- `com.traderx.markets.research-schedule-updated.v1`;
- `com.traderx.markets.research-occurrence-started.v1` and
  `com.traderx.markets.research-occurrence-skipped.v1`;
- `com.traderx.markets.coordinated-research-completed.v1` and
  `com.traderx.markets.category-research-blocked.v1`;
- `com.traderx.markets.source-fallback-applied.v1`;
- `com.traderx.markets.model-selection-changed.v1`; and
- the analysis completed, unavailable, and retry-requested facts.

Payloads contain stable IDs, policy/model pins, reason codes, hashes, and the explicit
`active_assignment_changed: false`/`authoritative: false` boundaries. They contain no credentials,
account balances/equity, or order intent.

## Release consequence

The FR-095–FR-105 amendment contract is reconciled. FR-106–FR-107 now have an initial runtime
implementation, but their value-ingestion, generated-client, complete contract/browser, and release
evidence tasks remain open. The broader original T245 gate remains partial because the entire 64-path
hand-authored design and pre-amendment event catalogue have not been collapsed into one generated
source. Production approval remains blocked.
