# Data Lifecycle

Structured account, decision, approval, policy, risk, agent-execution, broker, and audit records are retained for the configured regulatory and prop-firm evidence period. Append-only audit evidence is never edited in place. Market observations may be compressed after the hot period; derived features retain source/version references.

Users can export account configuration, strategies, journal, approvals, and performance in a portable archive. Account deletion first revokes sessions and provider connections, cryptographically destroys credential envelope keys, deletes owner blobs and knowledge vectors, and schedules structured personal-data erasure. Legally required audit evidence is minimized, pseudonymized, access restricted, and retained only for its declared period.

Deletion and export jobs are idempotent, audited, owner scoped, and expose progress. Backups expire on their documented schedule; deleted secrets cannot be recovered because their wrapping key is destroyed immediately.
