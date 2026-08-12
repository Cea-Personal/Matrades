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
