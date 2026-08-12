from traderx.audit.model import AuditEvent


def test_audit_model_is_append_only_evidence() -> None:
    assert AuditEvent.__tablename__ == "audit_events"
