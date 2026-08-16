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

### MetaTrader 5 Terminal-Bridge Profile

TraderX V1 uses the native `TraderXReadOnlyBridge.mq5` Expert Advisor. It is attached by the user to
one MT5 terminal/account and makes outbound HTTPS requests to TraderX; TraderX does not host a
generic MT5 socket/REST bridge and does not connect inbound to the terminal. The investor password
is entered only into MT5 and is never requested, persisted, or returned by TraderX.

An authorized owner first records the exact MT5 login and broker server. TraderX issues a
single-use, 24-hour enrollment code for one agent identity. The EA exchanges that code for a
random agent credential; both are retained by TraderX only as digests, rotation invalidates the
prior credential, and UI/API responses never return an active agent credential.

The EA may send only these read-only snapshot sections:

```text
terminal/account identity and health
account balance, equity, currency, and terminal version
open positions
overlapping immutable deal history
instrument metadata and contract specifications
current bid/ask/spread and visible broker-supported symbol universe
versioned bar/tick activity and broker-supplied real volume where available
optional broker Depth of Market with explicit unsupported/unavailable status
```

The EA source contains no order creation, check, modification, cancellation, closure, or terminal
state-changing call. Every enrollment and snapshot proves the configured login/server, terminal
connectivity, investor authorization, and disabled trading. Account mismatch, disconnect,
trading-enabled state, expired/invalid credential, stale response, or incomplete snapshot is a
failed observation, never an empty portfolio.

There is no MT5 transaction cursor assumption. Reconciliation polls one terminal/account at a time,
upserts positions by terminal ticket/identifier, and deduplicates deal history by immutable deal
ticket plus account/server over an overlapping window. It retains source/observation time and runs
periodic fuller lookbacks. Static and contract tests validate the EA's narrow denied capability
surface, enrollment identity, HTTPS-only transport, schema, freshness, and account binding.

MT5 price, tick volume, quote frequency, real volume, and DOM retain `BROKER_PROXY` semantics for
market research unless a reviewed exchange mapping proves otherwise. DOM collection uses
`MarketBookAdd`/`MarketBookGet` only for symbols where MT5 confirms it is available; absence is not
zero liquidity and MT5 DOM is never described as a consolidated Forex book.

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
describe_catalogue_profile()
test_connection()
list_capabilities()
discover_instruments(category, venue)
get_instrument_metadata(provider_symbol)
get_historical_observations(provider_symbol, kind, interval, range, cursor)
get_current_observations(provider_symbol, kind_set)
get_order_book_snapshot(provider_symbol, depth)  # explicit UNSUPPORTED is valid
stream_observations(provider_symbol_set, kind_set, cursor)
get_data_health(provider_symbol, kind, interval)
```

Canonical kinds include candle, tick, quote, spread, volume/turnover, order-book snapshot,
economic event, and macro observation. A provider declares supported kinds and volume semantics;
TraderX never treats FX tick volume, exchange traded volume, and turnover as equivalent.

Candles use `[start, end)` intervals, explicit price basis, completeness, and revision. Provider
corrections create superseding canonical revisions. Missing intervals and transformations are
reported, not silently hidden.

Every response also identifies catalogue/adapter/integration/venue, declared capability,
`ACTUAL`/`BROKER_PROXY`/`UNAVAILABLE` semantics, instrument mapping revision, entitlement tier,
source/event/receive time, freshness-policy reference, completeness, and revision. Initial reviewed
profiles are `CME_GROUP` for Commodity, `CBOE_FX_SPOT` for Forex, and `COINBASE_EXCHANGE` for
Cryptocurrency. MT5 remains authoritative for broker eligibility.

Ordered failure handling is per category: bounded specialist retries, current complete MT5
evidence, then complete cached external evidence inside the unchanged freshness policy, otherwise
`BLOCKED`. Adapters cannot weaken a gate or extend freshness during an outage.

## LLM Analysis Port

```text
test_connection()
describe_permitted_models()
analyze(
  pinned_provider,
  exact_model_id,
  catalogue_revision,
  adapter_revision,
  inference_policy_version,
  prompt_template_version,
  output_schema_version,
  normalized_evidence_manifest,
  deterministic_result_manifest,
  idempotency_key,
  timeout
)
```

The first reviewed profiles are `OPENAI_RESPONSES/gpt-5.6-terra` and
`ANTHROPIC_MESSAGES/claude-sonnet-5`. Model-list operations verify credential access only and cannot
admit a model outside the static catalogue. The normalized result includes exact requested/returned
model ID, provider request ID, validated advisory analysis, anomalies/cautions/explanations/method
proposals, usage/latency, output hash, and a redacted failure classification.

The port exposes no tools, browsing, file/MCP/code/shell execution, credentials, arbitrary URLs,
ranking operation, activation, risk change, or financial mutation. Response schemas contain no
field that can change eligibility, metrics, weights, score, rank, selection proposal, active market,
risk, or order state. Three TraderX-owned attempts are allowed; exhaustion returns a visible
unavailable state, never an alternative model.

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
- incremental historical synchronization without overwriting evidence;
- absence of callable real-money order methods in broker implementations;
- MT5 native-EA enrollment identity, investor-mode/trading-disabled checks, rejected null responses,
  account/server match, overlapping-deal reconciliation, broker-specific evidence labels, optional
  DOM, and denied terminal API surface;
- specialist entitlement loss, provider retirement, capability negotiation, asset-aware mandatory
  evidence, source conflicts, unchanged freshness during outage, and ordered fallback; and
- LLM model allowlisting/pinning, secret/data minimization, strict local schema validation, refusal,
  truncation, rate limit/timeout, deterministic-output immutability, and no automatic substitution.
