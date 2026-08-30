# Adapter Contracts

**Contract family**: `matrades.adapter.v1`

All external systems implement provider-neutral ports. Domain modules depend on these contracts, not
provider SDKs. Every response includes connection ID, adapter/schema version, source and received
times, health/freshness, provenance, correlation ID, and structured error details.

## Common Behavior

- Inputs and outputs are typed, versioned, and secret free.
- Calls enforce owner/account scope and bounded timeout/retry/rate-limit policy.
- Mutating broker calls require a valid ExecutionAuthorization, stable command/idempotency identity,
  expected broker object version, current safety epoch, and account scope.
- Streams detect duplicates, gaps, out-of-order messages, schema changes, and stale heartbeats.
- Recovery uses bounded exponential backoff with jitter and exposes DEGRADED/STALE/OFFLINE state.
- Provider symbols map to immutable internal instrument, exact venue-listing, instrument-type, and
  effective specification-version IDs before persistence or agent use.
- Raw provider payloads may be retained as protected evidence, but normalized contracts are canonical
  for application consumers.

## AgentRuntimeAdapter

```text
health(connection)
list_models(connection)
invoke(model, messages, tools, response_schema, parameters, deadline)
```

Returns selected and actual runtime, actual provider/model, usage, latency, finish/error reason,
structured output or validation error, and runtime request/thread ID. Matrades, not either runtime,
owns model, profile, credential, agent, prompt, permission, and fallback configuration.

`CodexAppServerRuntimeAdapter` is the default for every required agent. Agent workers use the stable
Python Codex SDK to control its pinned local App Server over stdio; runtime processes are supervised,
bounded, and health checked. The V1 adapter does not expose the experimental remote WebSocket
transport.

`LiteLLMRuntimeAdapter` is optional. It can be invoked only when the active agent configuration or
its explicitly selected model profile has runtime `LITELLM`. Merely configuring the gateway or
synchronizing models cannot select it. Fallback models MUST share the selected runtime, and the
runtime router MUST return an unavailable/degraded error instead of crossing runtimes automatically.

Contract tests prove default Codex selection, explicit LiteLLM opt-in, same-runtime fallback,
process restart/idempotency, runtime/model capability validation, and prohibition of automatic
Codex-to-LiteLLM or LiteLLM-to-Codex fallback.

## MarketDataAdapter

```text
health(connection)
capabilities(connection)
discover_instruments(connection, asset_class, instrument_type, as_of)
get_instrument_details(connection, venue_instrument, as_of)
get_quote(venue_instrument, as_of)
get_trades(venue_instrument, interval)
get_candles(venue_instrument, timeframe, interval)
get_order_book(venue_instrument, depth, as_of)
get_futures_chain(connection, underlying, as_of)
get_open_interest(venue_instrument, interval)
get_funding_or_financing(venue_instrument, interval)
get_corporate_actions(underlying, interval)
subscribe(venue_instruments, channels, resume_token)
```

Normalized records carry underlying, canonical instrument, exact venue listing or dated futures
contract, asset class, instrument type, effective instrument-specification version, source event/
sequence, source/received time, normalization version and quality. Continuous futures series are
marked analytical and never returned as executable listings. One shared connection manager and
immutable source cut serve consumers across account research schedules.

Provider selection is capability based: account → research lane → required capability → explicit
provider binding → healthy connection → verified canonical mapping. The broker/MT5 listing and terms
are authoritative for an executable CFD; a spot or futures venue may provide reference evidence but
cannot silently replace the CFD quote or terms. Coinbase, Twelve Data, CoinGecko, a futures-chain
provider, and future adapters expose only the capabilities they actually support.

Contract tests cover reconnect, backoff, rate limits, dedupe, reorder window, gap detection/backfill,
instrument mapping, contract/specification versioning, decimal precision, order-book sequence,
staleness, futures expiry/roll, corporate actions, financing, shared-cut reuse, quota enforcement,
and prohibition of cross-instrument-type substitution.

## Macro, Positioning, Calendar, and News Adapters

```text
MacroDataAdapter.get_series(series, interval, vintage)
PositioningAdapter.get_observations(instrument_or_market, interval)
CalendarAdapter.get_events(scope, interval)
NewsAdapter.search(scope, interval, filters)
```

Calendar events preserve source ID/version, scheduled UTC and source timezone, importance, affected
country/currency, previous/forecast/actual, release/revision status, retrieved time, freshness and
parser version. A scraper remains behind CalendarAdapter, records terms/source provenance and schema
health, and never runs inside an agent.

## BrokerAdapter

Read, capability, reconciliation, and bounded write surface:

```text
health(account_connection)
capabilities(account_connection)
get_account(account_connection)
get_positions(account_connection)
get_orders(account_connection)
get_deals_or_fills(account_connection, interval, watermark)
get_history(account_connection, interval, watermark)
list_instruments(account_connection, asset_class, instrument_type)
get_quote(account_connection, venue_instrument, as_of)
get_symbol_info(account_connection, venue_instrument, as_of)
get_command_status(account_connection, command_id)
subscribe_events(account_connection, resume_token)

submit_order(command_id, authorization, order, expected_account_version)
cancel_order(command_id, authorization, broker_order_id, expected_order_version)
set_or_modify_stop_loss(command_id, authorization, position_id, value, expected_position_version)
set_or_modify_take_profit(command_id, authorization, position_id, value, expected_position_version)
partial_close(command_id, authorization, position_id, quantity, expected_position_version)
close_position(command_id, authorization, position_id, expected_position_version)
```

Broker snapshots include a provider cut/sequence so equity, positions and orders can be validated for
consistency. Events include ORDER_ACCEPTED, ORDER_REJECTED, ORDER_CANCELLED, PARTIAL_FILL,
FILL_COMPLETED, FILL_CORRECTED, POSITION_OPENED, POSITION_CHANGED, POSITION_CLOSED, SL_CHANGED,
TP_CHANGED, PROTECTION_EXECUTED, and ACCOUNT_CHANGED. Actual reconciled values supersede planned
values. A successful transport response never implies order acceptance or fill unless broker evidence
is included and later reconcilable.

Mutating methods reject expired authorization, wrong account/action, disabled permission, active or
stale kill-switch epoch, missing capability, stale expected broker version, mismatched symbol/
contract, unsafe normalized values, or a repeated command ID with a different payload. The same
command ID and payload returns the recorded outcome. Timeout after possible submission returns
`OUTCOME_UNKNOWN`; the application reconciles orders, fills, positions, and history before retry.

The MT5 bridge adapter authenticates the bridge, verifies heartbeat, deduplicates/resumes events,
normalizes broker symbols and times, and publishes effective-dated symbol properties including
contract size, tick size/value, volume bounds/step, currencies, margin mode, swap/financing, fill
mode, netting/hedging mode, trading permissions, freeze/stops levels, and expiry. Matrades writes a
signed command to the Python bridge's durable queue; the MQL5 EA polls through outbound `WebRequest`,
validates account/authorization/expiry/nonce/safety epoch and requested bounds, calls MT5, and posts
receipts, results, and events. The bridge uses transactional leasing and a restart-safe local command/
event ledger. Missing critical properties block construction or sizing. Remote deployments use mTLS;
loopback/private deployments use scoped HMAC credentials with timestamp, nonce, method, path, and
body digest. Broker credentials never enter an agent process.

Contract tests cover command replay with same/conflicting payload, bridge/EA restart during dispatch,
lost response, partial and out-of-order fills, cancel/fill and protection races, expected-version
conflicts, permission denial, kill-switch fencing, expiry, wrong account/type/contract, raw credential
isolation, and reconciliation-before-retry.

## EmbeddingProvider and SemanticIndex

```text
EmbeddingProvider.health()
EmbeddingProvider.embed_documents(content[])
EmbeddingProvider.embed_query(query)

SemanticIndex.upsert(generation, authorized_segments[])
SemanticIndex.search(vector, authorization_scope, metadata_filters, limit)
SemanticIndex.delete(source_or_generation)
SemanticIndex.health()
```

Vectors retain model, version and dimension. Search applies authorization and active-generation
filters before ranking. Failure degrades contextual research only and cannot alter structured safety.

## BlobStore

```text
put(owner_scope, content, checksum, media_type)
get(owner_scope, object_id)
delete(owner_scope, object_id)
health()
```

Used only when uploaded documents or large artifacts are unsuitable for relational storage. Objects
are encrypted, checksummed, access audited, and referenced by opaque ID.

## NotificationAdapter

```text
send(destination_reference, notification, idempotency_key)
status(provider_message_id)
health(connection)
```

In-product notifications are authoritative for the UI. Telegram and Pushover are required V1
delivery adapters; browser, email, and future channels use the same replaceable contract. Delivery
or acknowledgment never changes execution state. A provider timeout may produce `UNKNOWN_DELIVERY`;
retries reuse the same delivery identity and do not create a new logical notification.

## Health and Error Contract

Statuses: `HEALTHY`, `DEGRADED`, `STALE`, `OFFLINE`, `DISABLED`.

Errors contain stable code, retryability, provider code (redacted), safe message, source time,
correlation ID, and affected capability. Adapters never return fabricated empty success on failure.
The application maps health/freshness to BLOCK or DEGRADED using versioned policy.
