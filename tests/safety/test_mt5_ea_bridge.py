from pathlib import Path

EA_SOURCE = (
    Path(__file__).parents[2]
    / "apps"
    / "mt5_bridge"
    / "mql5"
    / "TraderXReadOnlyBridge.mq5"
)


def test_native_mt5_ea_has_only_fixed_outbound_read_only_operations() -> None:
    source = EA_SOURCE.read_text(encoding="utf-8")

    assert 'PostJson("configuration"' in source
    assert 'PostJson("enroll"' in source
    assert 'PostJson("snapshots"' in source
    assert "TERMINAL_TRADE_ALLOWED" in source
    assert "ACCOUNT_TRADE_ALLOWED" in source
    assert "ACCOUNT_TRADE_EXPERT" not in source
    assert "HistorySelect(" in source
    assert "PositionGetTicket(" in source

    for forbidden in (
        "OrderSend(",
        "OrderCheck(",
        "OrderDelete(",
        "OrderModify(",
        "PositionClose(",
        "PositionOpen(",
        "CTrade",
        "SymbolSelect(",
    ):
        assert forbidden not in source
