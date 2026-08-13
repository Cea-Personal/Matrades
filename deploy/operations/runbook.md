# TraderX operator runbook

## Migrate

Run the one-shot `migrate` service before starting API or worker roles. Review the generated
Alembic plan in staging first; ordinary downgrade is intentionally prohibited because evidence is
retained.

## Backup and restore

Take encrypted PostgreSQL and immutable-artifact backups off-host. Restore into an isolated
environment, verify database row counts, artifact checksums, audit-chain integrity, outbox replay,
and worker recovery before a recovery declaration.

## Key rotation

Create a new AES-GCM key version in the secret manager, re-encrypt active credentials, verify
decryptability, mark the prior key decrypt-only for the retention window, then revoke it. Secrets
are write-only in the UI and must not enter logs, exports, or audit payloads.

## MT5 bridge

Create or renew the managed MT5 enrollment in Command Center, download and compile
`TraderXReadOnlyBridge.mq5` inside the MT5 terminal, and configure the single TraderX HTTPS origin
under **Tools → Options → Expert Advisors → Allow WebRequest**. For local macOS/Wine MT5, add
`https://127.0.0.1:3000` rather than `localhost`. The EA is outbound-only and does
not listen on any port. Keep Auto Trading disabled and use an investor-password account. A terminal
that is disconnected or reports terminal, account, or EA trading enabled is rejected. If evidence
stops arriving, the snapshot expires after 90 seconds and TraderX remains in LOCKDOWN. Treat a lost
EA state file as a credential-rotation event: select **Reconnect MT5 bridge** in Command Center and
attach the EA using the new setup code.
