# TraderX Provider Port Contracts

Provider ports isolate external systems from TraderX domain rules. Adapters may differ by provider,
but normalized outputs, quality metadata, idempotency, and failure classifications are stable.

## Common Observation Envelope

Every provider observation contains:

- provider and integration identity;
- canonical and provider instrument/account identity;
- provider event identity or documented deterministic fingerprint;
- provider sequence/revision when available;
- market/event time, provider publication time, received time, and ingested time;
- completeness/finality and normalization/schema versions;
- quality flags and raw immutable record reference; and
- correlation and trace identifiers.

Provider errors are classified as `AUTHENTICATION`, `AUTHORIZATION`, `RATE_LIMIT`, `TRANSIENT`,
`PERMANENT_INPUT`, `UNSUPPORTED`, `STALE`, `CONTRADICTORY`, or `UNKNOWN`. Adapters redact secrets
before returning or logging failures.

## Broker Read Port

Required V1 capabilities:

```text
test_connection()
get_account_snapshot(account_ref)
list_instruments(account_ref)
get_instrument_spec(account_ref, provider_symbol)
get_open_positions(account_ref)
get_deals(account_ref, cursor_or_range)
get_account_changes(account_ref, cursor)  # returns UNSUPPORTED if no documented delta protocol exists
```

Normalized outputs:

- `AccountSnapshot`: balance, equity, realized/floating P&L, margin, free margin, currency, time,
  quality, completeness, and provider identity;
- `PositionSnapshot`: provider position ID, instrument, direction, volume, average entry, current
  observed stop/targets, open/close state, times, and revision;
- `Deal`: immutable fill identity, position/order references where the provider supplies them,
  side, volume, price, fees, currency, and time;
- `InstrumentSpec`: contract size, tick size/value and currency, price/volume precision, minimum and
  maximum volume, step, sessions, and restrictions; and
- `Quote`: bid, ask, last where available, price basis, sequence, and freshness.

### Constitutional Negative Capability

The V1 broker port MUST NOT define or expose any of the following:

```text
submit_live_order
modify_live_order
cancel_live_order
close_live_position
```

Adapters that require broad provider credentials MUST still enforce the read-only capability
allowlist inside TraderX. Connection testing fails if the configured use cannot be limited safely.

### OANDA v20 Adapter Profile

The OANDA adapter uses only the official v20 REST host selected by integration environment:
`https://api-fxpractice.oanda.com` for `PRACTICE` and `https://api-fxtrade.oanda.com` for `LIVE`.
It accepts a write-only Personal Access Token and first calls `GET /v3/accounts` to discover the
accounts accessible to that credential. A TraderX account cannot bind until its owner selects one
returned `accountID`.

- Bootstrap with `GET /v3/accounts/{accountID}`. Normalize its account, open positions, and open
  trades as one coherent snapshot; map OANDA `NAV` to TraderX `equity`; save `lastTransactionID`.
- Increment with `GET /v3/accounts/{accountID}/changes?sinceTransactionID={cursor}`. Apply both
  transaction-derived `changes` and price-dependent `state`; advance the cursor only with a
  complete successful normalization.
- Cross-check current risk with `GET /v3/accounts/{accountID}/openPositions` and, when needed,
  `GET /v3/accounts/{accountID}/openTrades`. Use documented transaction history pages/ranges for
  audit recovery; transaction identities are immutable source IDs.
- Allow only reviewed GET methods for account, position, trade, transaction, and instrument reads.
  The adapter has no generic HTTP method/path escape hatch. On invalid cursor, selected-account
  mismatch, unsuccessful validation, 401/403/404, exhausted 429 retry, TLS/network failure, or
  stale data, it records evidence and demands a new complete bootstrap.

The provider credential may be capable of more than reading. Its scope is therefore not an
authorization claim made by TraderX; the endpoint/method allowlist, secret handling, and outbound
egress restriction are mandatory compensating controls. See OANDA's
[account model](https://developer.oanda.com/rest-live-v20/account-ep/) and
[account-change guidance](https://developer.oanda.com/rest-live-v20/best-practices/).

### MetaTrader 5 Terminal-Bridge Profile

The MT5 adapter communicates only with a registered bridge over mutually authenticated HTTPS. The
bridge is co-located with one provisioned MT5 terminal and owns that terminal's investor/read-only
password. TraderX sends no order intent and never persists or returns the MT5 password.

The bridge must expose only these read operations to the TraderX adapter:

```text
get_health_and_terminal_state()
get_account_snapshot()
get_open_positions()
get_deals(overlapping_time_range)
list_instruments()
get_instrument_spec(provider_symbol)
get_quote(provider_symbol)  # optional
```

Internally, the bridge may use only terminal lifecycle/diagnostic APIs, `terminal_info`,
`account_info`, `positions_get`, `history_deals_get`, `symbols_get`, `symbol_info`, and optional
`symbol_info_tick`. It MUST NOT invoke `order_send`, `order_check`, `order_calc_margin`,
`order_calc_profit`, `symbol_select`, scripts, EAs, or any other state-changing terminal function.
Every response proves the configured login/server, terminal connectivity, and `trade_allowed =
false` for account and terminal. A `None`/missing MT5 result, account mismatch, disconnect,
trading-enabled flag, non-fresh response, or incomplete snapshot is a failed observation, never an
empty portfolio.

There is no MT5 transaction cursor assumption. Reconciliation polls one terminal/account at a time,
upserts positions by terminal ticket/identifier, and deduplicates deal history by immutable deal
ticket plus account/server over an overlapping window. It retains source/observation time and runs
periodic fuller lookbacks. The bridge validates its narrow contract and denied API surface in CI;
the core adapter validates mTLS identity, response schema, freshness, and account binding.

### Reconciliation

- Begin with an authoritative account/position snapshot.
- Apply documented account-change/delta protocols for latency where supported; otherwise use the
  provider's bounded polling protocol.
- Poll authoritative snapshots periodically and after reconnect or detected sequence gaps.
- Preserve every partial fill/deal independently.
- Duplicate/out-of-order inputs are evidence but cannot regress the current projection.
- Contradictions, sequence gaps, unknown equity, stale position state, or failed reconciliation set
  the broker capability to degraded/failed and block new live recommendations.

## Market Data Port

Required capabilities:

```text
discover_instruments(category)
get_instrument_metadata(provider_symbol)
get_historical_observations(provider_symbol, kind, interval, range, cursor)
stream_observations(provider_symbol_set, kind_set, cursor)
get_data_health(provider_symbol, kind, interval)
```

Canonical kinds include candle, tick, quote, spread, volume/turnover, order-book snapshot,
economic event, and macro observation. A provider declares supported kinds and volume semantics;
TraderX never treats FX tick volume, exchange traded volume, and turnover as equivalent.

Candles use `[start, end)` intervals, explicit price basis, completeness, and revision. Provider
corrections create superseding canonical revisions. Missing intervals and transformations are
reported, not silently hidden.

## Notification Port

```text
test_connection()
send(notification_id, recipient, rendered_content, idempotency_hint)
query_delivery(provider_message_id)  # optional
```

The result is `SENT`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`, or `AMBIGUOUS`, with provider
message ID, retry-after time, and redacted reason. External exactly-once delivery is not promised.
Critical events always remain in the durable web inbox even if all external channels fail.

## Artifact Port

```text
put_immutable(content_stream, media_type, checksum, classification)
open_authorized(artifact_ref, actor)
verify(artifact_ref, checksum)
```

Used for large dataset snapshots, reports, equity curves, and journal attachments. PostgreSQL
stores manifests and authorization metadata. Content is immutable and addressed by checksum;
replacement creates a new artifact reference.

## Clock and Calendar Ports

Safety and reproducibility code receive explicit clock/calendar dependencies:

```text
now_utc()
trading_session(instrument, instant, calendar_version)
account_trading_day(account, instant, reset_rule_version)
```

Backtests use a replay clock; paper/live recommendation paths use a monotonic-aware production
clock. IANA time-zone and calendar versions are preserved in run manifests.

## Adapter Qualification Tests

Every adapter MUST pass contract tests for:

- secret redaction and authentication failure;
- duplicate and out-of-order events;
- reconnect and cursor/sequence gaps;
- partial fills and provider corrections;
- UTC/DST and precision boundaries;
- stale, missing, contradictory, and incomplete data;
- rate limits, retry-after behavior, timeouts, and ambiguous outcomes;
- canonical instrument alias/specification mapping;
- incremental historical synchronization without overwriting evidence; and
- absence of callable real-money order methods in broker implementations.
- OANDA practice/live host selection, selected-account binding, GET-only allowlist, transaction
  cursor recovery, and `NAV`-to-equity evidence;
- MT5 bridge mTLS identity, investor-password/trading-disabled checks, rejected null responses,
  account/server match, overlapping-deal reconciliation, and denied terminal API surface.
