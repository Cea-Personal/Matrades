from adapters.market_data.coinbase.stream import SequenceGuard


def test_sequence_gap_requires_resync():
    guard = SequenceGuard()
    assert guard.accept(10)
    assert not guard.accept(12)
    assert guard.needs_resync
    guard.reconnect(20)
    assert guard.accept(21)


def test_new_stream_is_stale_until_data():
    assert SequenceGuard().stale
