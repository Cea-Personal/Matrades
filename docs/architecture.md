# Matrades Architecture

Matrades is a modular monolith with FastAPI, Celery, a dedicated agent worker, Next.js, PostgreSQL/TimescaleDB/pgvector, and Redis. PostgreSQL is authoritative for workflows, approvals, versions, reservations, jobs, audit, and the transactional outbox. Redis is only cache, lock, rate-limit, and delivery acceleration. SSE projects outbox events and never becomes a system of record.

Deterministic services own account truth, financial math, effective-policy selection, risk decisions, strategy compilation, lifecycle transitions, reconciliation, and performance. Agent roles interpret bounded evidence. The fifteen protected logical agents use `CODEX_APP_SERVER` by default. A versioned agent/profile assignment may select `LITELLM_GATEWAY`; fallbacks must remain within that runtime and exhaustion fails safely. System and user prompts independently resolve agent override → orchestrator → platform. Tool permissions are separately versioned and forbid broker writes, hard-policy or guardrail mutation, raw credentials, and strategy activation.

The MT5 bridge exposes account, positions, orders/history, symbol data, heartbeat, and capabilities as authenticated read-only records. HIL-1 selects markets, HIL-2 records TAKE/WAIT/REJECT, and HIL-3 records management intent. TAKE/APPROVE never sends an order or modifies a position.

External adapters implement timeouts, freshness, provenance, rate limits, health, and closed circuit breakers. Knowledge retrieval is owner scoped and context-only; current account, market, policy, risk, strategy identity, and performance facts always route to structured stores.
