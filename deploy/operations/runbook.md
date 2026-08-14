# TraderX operator runbook

## Migrate

Run the one-shot `migrate` service before starting API or worker roles. Review the generated
Alembic plan in staging first; ordinary downgrade is intentionally prohibited because evidence is
retained.

Provision `session_pepper` and `encryption_key_b64` as external Docker secrets before the first
production start. Generate both with an approved password/key generator and secret manager; do not
place their plaintext in this repository, command history, or Compose environment values.

```sh
docker compose -f deploy/compose.production.yaml config --quiet
docker compose -f deploy/compose.production.yaml run --rm migrate
docker compose -f deploy/compose.production.yaml up -d
docker compose -f deploy/compose.production.yaml ps
```

Do not start API or worker roles after a failed migration. Record the revision, database backup
identifier, approver, and migration output in the change record.

## Backup and restore

Take encrypted PostgreSQL and immutable-artifact backups off-host. Restore into an isolated
environment, verify database row counts, artifact checksums, audit-chain integrity, outbox replay,
and worker recovery before a recovery declaration.

1. Put workers into checkpointed pause and record queue depths and the Alembic revision.
2. Run `pg_dump --format=custom --no-owner traderx`, encrypt the dump with an approved off-host
   KMS recipient, and upload the ciphertext plus a SHA-256 manifest. Never retain the plaintext.
3. Back up artifact manifests and objects separately, preserving content hashes.
4. Restore into a new isolated PostgreSQL instance with no broker or notification egress.
5. Run `alembic upgrade head`, compare governed table counts, validate audit integrity hashes and
   artifact checksums, then replay a copy of pending outbox work into disabled test adapters.
6. Record recovery-point and recovery-time results. Production recovery requires owner approval;
   it must not silently reconnect MT5 or enable recommendations.

## Key rotation

Create a new AES-GCM key version in the secret manager, re-encrypt active credentials, verify
decryptability, mark the prior key decrypt-only for the retention window, then revoke it. Secrets
are write-only in the UI and must not enter logs, exports, or audit payloads.

Key rotation is fail closed: retain the previous key until every active envelope decrypts under
the new version and a redaction scan passes. If verification fails, stop rotation, keep integrations
disabled, and restore the previous decrypt-only key; never copy plaintext into a shell argument.

## Incident recovery

Use the Operations workspace to inspect circuit breakers, failed jobs, data freshness, and the
redacted audit trail. Disable the affected integration from the UI. Preserve the last good snapshot
for audit but do not treat it as current. Resume or retry jobs only from their advertised safe
actions. Re-enable recommendations only after account data is verified and every breaker has an
authorized, evidenced clearing decision.

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
