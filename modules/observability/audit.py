"""Durable audit authority.

Audit records are persisted transactionally by ``ResourceStore``.  This module
intentionally exposes no process-local append-only log.
"""

from packages.shared.store import AuditRecord

__all__ = ["AuditRecord"]
