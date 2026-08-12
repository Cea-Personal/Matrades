from traderx.monitoring.reconciliation import ProviderEvent, reconcile


def test_reconciliation_deduplicates_and_identifies_sequence_gaps() -> None:
    result = reconcile(
        [ProviderEvent("a", 3, {}), ProviderEvent("a", 3, {}), ProviderEvent("b", 4, {})],
        last_sequence=1,
    )
    assert [event.event_id for event in result.accepted] == ["a", "b"]
    assert "PROVIDER_SEQUENCE_GAP" in result.reason_codes
