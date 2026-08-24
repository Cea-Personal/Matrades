# Adapter Contracts

**Contract family**: `matrades.adapter.v1`

All external systems implement provider-neutral ports. Domain modules depend on these contracts, not
provider SDKs. Every response includes connection ID, adapter/schema version, source and received
times, health/freshness, provenance, correlation ID, and structured error details.

## Common Behavior

- Inputs and outputs are typed, versioned, and secret free.
- Calls enforce owner/account scope and bounded timeout/retry/rate-limit policy.
- Mutating adapter calls require an idempotency key; V1 BrokerAdapter exposes no mutating calls.
- Streams detect duplicates, gaps, out-of-order messages, schema changes, and stale heartbeats.
- Recovery uses bounded exponential backoff with jitter and exposes DEGRADED/STALE/OFFLINE state.
- Provider symbols map to immutable internal instrument IDs before persistence or agent use.
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
list_instruments(connection)
get_quote(instrument, as_of)
get_trades(instrument, interval)
get_candles(instrument, timeframe, interval)
get_order_book(instrument, depth, as_of)
subscribe(instruments, channels, resume_token)
```

Normalized stream records carry instrument/venue IDs, source event ID/sequence, source/received time,
normalization version and quality. One shared connection manager serves consumers. Coinbase is the V1
crypto exchange adapter; Twelve Data covers Forex/metals; CoinGecko is discovery/metadata and cannot
substitute for an exchange-level current quote.

Contract tests cover reconnect, backoff, rate limits, dedupe, reorder window, gap detection/backfill,
instrument mapping, decimal precision, order-book sequence, staleness, and provider substitution.

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

V1 read-only surface:

```text
health(account_connection)
get_account(account_connection)
get_positions(account_connection)
get_orders(account_connection)
get_history(account_connection, interval)
get_symbol_info(account_connection, instrument)
subscribe_events(account_connection, resume_token)
```

Broker snapshots include a provider cut/sequence so equity, positions and orders can be validated for
consistency. Events include POSITION_OPENED, POSITION_CHANGED, POSITION_CLOSED, SL_CHANGED,
TP_CHANGED, PROTECTION_EXECUTED, and ACCOUNT_CHANGED. Actual reconciled values supersede proposal
values. No method opens, changes, or closes a position in V1.

The MT5 bridge adapter authenticates the bridge, verifies heartbeat, deduplicates/resumes events,
normalizes broker symbols and times, and marks state stale on disconnect. Remote deployments use
mTLS; loopback-only deployments use a rotating scoped token.

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

In-product notifications are authoritative for the UI. Browser, email, Telegram and future channels
are delivery adapters; delivery or acknowledgment never resolves an approval.

## Health and Error Contract

Statuses: `HEALTHY`, `DEGRADED`, `STALE`, `OFFLINE`, `DISABLED`.

Errors contain stable code, retryability, provider code (redacted), safe message, source time,
correlation ID, and affected capability. Adapters never return fabricated empty success on failure.
The application maps health/freshness to BLOCK or DEGRADED using versioned policy.
