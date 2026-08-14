# Constitution compliance check

Checked on 2026-08-14.

Automated implementation status: **PASS**. Production-release status:
**BLOCKED / NOT APPROVED**.

## Passing governed boundaries

- Manual execution: provider, API, worker, EA, and source guards expose no operation that submits,
  modifies, cancels, or closes a live order.
- Market selection: data, liquidity, execution, broker, prop, and sizing eligibility precede
  ranking; exactly one Commodity, Forex pair, and Cryptocurrency pair may be deliberately active;
  no result silently replaces an assignment.
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

- Ruff and strict Mypy pass (130 typed source files).
- All 159 Python tests pass.
- All 3 web component tests and 19 Playwright journeys pass.
- The optimized Next.js build and both Compose configurations render successfully.
- Fresh migration rehearsal reaches `0022_authentication_throttles`.
- The existing PostgreSQL database migrated transactionally from `0014` to `0022` after correcting
  and regression-testing Alembic's 32-character revision-ID limit.
- The running local PostgreSQL and Redis services are healthy, and the Caddy HTTPS API health route
  returns HTTP/2 200 with correlation and security headers.

## Release blockers

1. The hand-authored HTTP contract and 44-event catalog are not fully reconciled with runtime; see
   `contracts/compatibility-report.md`.
2. A real external MT5 demo-terminal reconciliation/freshness run has not been recorded.
3. An off-host encrypted backup/restore operator drill has not been recorded.
4. Production Email/Telegram delivery and deployment dynamic scanning have not been recorded.
5. Success criteria requiring external timing or moderated-user percentages do not yet have
   qualifying evidence; see `traceability.md`.

Because these are constitutional release gates, T245–T248 remain unchecked. Nothing in this check
authorizes deployment, guarantees profitability, or permits TraderX to execute a real-money trade.
