from pathlib import Path

EA_SOURCE = Path(__file__).parents[2] / "apps" / "mt5_bridge" / "mql5" / "TraderXReadOnlyBridge.mq5"


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


def test_native_mt5_ea_prefers_a_new_enrollment_code_over_stale_local_state() -> None:
    source = EA_SOURCE.read_text(encoding="utf-8")

    fresh_enrollment = source.index("if(StringLen(EnrollmentCode)>=32)")
    local_state_fallback = source.index("else if(!LoadState())")
    assert fresh_enrollment < local_state_fallback
    assert "if(!Enroll())" in source[fresh_enrollment:local_state_fallback]
