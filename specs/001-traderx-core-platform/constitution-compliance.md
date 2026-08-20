# Constitution compliance check

Checked on 2026-08-20.

Automated implementation status: **PASS**. Production-release status:
**BLOCKED / NOT APPROVED**.

## Passing governed boundaries

- Manual execution: provider, API, worker, EA, and source guards expose no operation that submits,
  modifies, cancels, or closes a live order.
- Market selection: data, liquidity, execution, broker, prop, and sizing eligibility precede
  ranking; exactly one Commodity, Forex pair, and Cryptocurrency pair may be deliberately active;
  no result silently replaces an assignment.
- Official source authority: the fixed CME/Cboe/Coinbase catalogue is purpose- and venue-specific;
  MT5 retains broker support/specification authority; every measure is labelled `ACTUAL`,
  `BROKER_PROXY`, or `UNAVAILABLE`; ambiguous/unentitled mappings and conflicts fail closed.
- Deterministic and AI authority: the deterministic engine alone owns gates, measures, scores,
  ranks, proposals, risk, and activation boundaries. OpenAI/Anthropic adapters expose no tools,
  receive minimized non-account evidence, use an exact pinned model/schema/policy, and cannot
  mutate the deterministic result. Failure remains visible and same-pin only.
- Scheduled coordination: PostgreSQL owns the anchored schedule, unique occurrence, overlap skip,
  lease, and exactly-three-child constraint. Browser/Celery timing is not authoritative, no catch-up
  weakens the overlap policy, and partial outcomes preserve every active assignment.
- Safety authority: the server Risk Manager can reduce or block a recommendation; missing critical
  data fails closed; dynamic capacity remains between zero and two.
- Evidence lifecycle: immutable strategies, chronological portfolio validation, current-data paper
  evidence, step-up human approval, frozen trade theses, append-only observations/journals, and
  controlled reactivation prevent automatic promotion or evidence deletion.
- Operations/security: authenticated role-gated routes, recent MFA for high-risk commands,
  idempotency/ETags, append-only audit integrity, envelope-encrypted secrets, durable throttling,
  hardened headers/containers, jobs, notification controls, health, and redacted observability are
  implemented in the current Command Center.
- Recovery: checksummed encrypted manifests preserve governed records, pending outbox work, and
  resumable jobs while forcing external integrations back to unverified/LOCKDOWN.

## Evidence executed

- Ruff and strict Mypy pass (147 typed source files).
- All 189 Python tests pass.
- All 3 web component tests and all 22 Playwright journeys pass, including the amended Markets,
  provider lifecycle, and accessibility scenarios.
- The optimized Next.js build and both Compose configurations render successfully.
- Fresh migration rehearsal reaches `0023_market_research_automation`.
- The existing PostgreSQL database migrated transactionally from `0014` to `0022` after correcting
  and regression-testing Alembic's 32-character revision-ID limit.
- The running local PostgreSQL and Redis services are healthy, and the Caddy HTTPS API health route
  returns HTTP/2 200 with correlation and security headers.

## Release blockers

1. The amendment HTTP/provider/event surface is reconciled, but the broader original hand-authored
   HTTP and pre-amendment event catalog are not one generated runtime source; see
   `contracts/compatibility-report.md`.
2. A real external MT5 demo-terminal reconciliation/freshness run has not been recorded.
3. An off-host encrypted backup/restore operator drill has not been recorded.
4. Production Email/Telegram delivery and deployment dynamic scanning have not been recorded.
5. Legally usable production CME/Cboe entitlements, provider retention approval, and a running
   browser-closed scheduler/worker restart drill have not been recorded.
6. Success criteria requiring external timing or moderated-user percentages do not yet have
   qualifying evidence; see `traceability.md`.

The amended Constitution Check was re-run and its decision is **BLOCKED / NOT APPROVED** until the
listed external gates pass. This recorded decision completes the check itself without
waiving T245/T246/T248/T260/T327. Nothing here authorizes deployment, guarantees profitability, or
permits TraderX to execute a real-money trade.
