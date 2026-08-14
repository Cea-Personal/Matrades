from traderx.monitoring.reconciliation import ProviderEvent, reconcile


def test_reconciliation_deduplicates_and_identifies_sequence_gaps() -> None:
    result = reconcile(
        [ProviderEvent("a", 3, {}), ProviderEvent("a", 3, {}), ProviderEvent("b", 4, {})],
        last_sequence=1,
    )
    assert [event.event_id for event in result.accepted] == ["a", "b"]
    assert "PROVIDER_SEQUENCE_GAP" in result.reason_codes


def test_overlap_out_of_order_and_provider_corrections_fail_closed() -> None:
    overlap = reconcile(
        [
            ProviderEvent("old", 4, {"profit": "1"}),
            ProviderEvent("new", 6, {"profit": "2"}),
            ProviderEvent("new", 6, {"profit": "2"}),
        ],
        last_sequence=5,
        known_event_ids=frozenset({"old"}),
    )
    assert [event.event_id for event in overlap.accepted] == ["new"]
    assert "OVERLAPPING_WINDOW_DEDUPLICATED" in overlap.reason_codes
    contradictory = reconcile(
        [
            ProviderEvent("deal-7", 7, {"volume": "1"}),
            ProviderEvent("deal-7", 7, {"volume": "2"}),
            ProviderEvent("different-id", 7, {"volume": "1"}),
        ],
        last_sequence=6,
    )
    assert "CONTRADICTORY_PROVIDER_EVENT" in contradictory.reason_codes
    assert "CONTRADICTORY_PROVIDER_SEQUENCE" in contradictory.reason_codes
