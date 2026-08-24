from pathlib import Path


def test_operations_ui_has_inbox_journal_performance_and_health():
    text = "".join(
        Path(x).read_text()
        for x in (
            "apps/web/src/features/approvals/ApprovalInbox.tsx",
            "apps/web/src/features/journal/JournalTimeline.tsx",
            "apps/web/src/features/performance/PerformanceDashboard.tsx",
            "apps/web/src/features/health/HealthDashboard.tsx",
        )
    )
    assert all(
        x in text
        for x in ("HIL-1", "Decision timeline", "Performance attribution", "Operational health")
    )
