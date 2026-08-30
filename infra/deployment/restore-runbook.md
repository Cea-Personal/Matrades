# Matrades Restore Runbook

Use a clean recovery environment and preserve the failed environment for evidence. Restore PostgreSQL from the latest verified base backup plus WAL to the requested point in time, then restore the owner-scoped blob snapshot matching that database recovery point.

1. Declare the incident, freeze all workers, and record the target recovery timestamp.
2. Provision PostgreSQL 17 with TimescaleDB and pgvector, restore the base backup, replay WAL, and stop at the target.
3. Run `alembic current`, verify migration `0012`, extension availability, row counts, ownership constraints, command/outbox continuity, kill-switch epochs, and audit hashes.
4. Restore encrypted blobs to a new bucket/root. Verify hashes and owner prefixes without printing content.
5. Start API read-only, then workers, Codex agent worker, and web. Keep provider and MT5 connections disabled until freshness checks pass.
6. Exercise fixture risk, autonomous Trade Plan authorization, reconciliation, journal, credential destruction, kill-switch fencing, and backup recovery probes.
7. Re-enable providers one at a time. LiteLLM remains off unless explicitly assigned profiles existed at the recovery point.

Quarterly restore drills must record recovery-point objective, recovery-time objective, evidence IDs, exceptions, and approver. Backups containing credential ciphertext require the same access controls as production; key backups are maintained separately.
