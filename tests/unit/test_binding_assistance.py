from uuid import uuid4

import pytest

from modules.connections.binding_assistance import (
    BindingAdvice,
    BindingChoice,
    binding_candidates,
    select_candidates,
)


def source(provider, capabilities, **overrides):
    return {
        "id": str(uuid4()),
        "version": 1,
        "state": "ACTIVE",
        "provider": provider,
        "name": provider,
        "health": "HEALTHY",
        "active": True,
        "capabilities": capabilities,
        "configuration": {},
        **overrides,
    }


def lane(asset, kind="CFD", enabled=True):
    return {"asset_class": asset, "instrument_type": kind, "enabled": enabled}


def test_recommendations_follow_actual_adapter_coverage_and_disabled_lanes():
    sources = [
        source("TWELVE_DATA", ["market.discovery", "candles.read"]),
        source("COINBASE", ["crypto.discovery", "candles.read"]),
        source(
            "MT5_BRIDGE", ["market.discovery", "quotes.read", "candles.read", "contract_terms.read"]
        ),
        source("SERPAPI", ["search.read", "youtube.discovery"]),
        source("OPENAI", ["responses.create"]),
    ]
    options, gaps = binding_candidates(
        {},
        [
            lane("FOREX"),
            lane("METALS"),
            lane("CRYPTOCURRENCY"),
            lane("STOCKS"),
            lane("METALS", "FUTURES"),
            lane("FOREX", "SPOT", False),
        ],
        sources,
        [],
    )
    selected = select_candidates(options)
    discovery = {c.lane["asset_class"]: c.provider for c in selected if c.capability == "DISCOVERY"}
    assert discovery == {
        "FOREX": "MT5_BRIDGE",
        "METALS": "MT5_BRIDGE",
        "CRYPTOCURRENCY": "COINBASE",
        "STOCKS": "TWELVE_DATA",
    }
    assert all(c.lane["instrument_type"] == "CFD" for c in selected)
    assert all(c.provider not in {"SERPAPI", "OPENAI"} for c in options)
    assert gaps[0]["lane"] == "METALS:FUTURES"
    assert "no futures discovery adapter" in gaps[0]["reason"]
    assert all(
        c.provider == "MT5_BRIDGE"
        for c in selected
        if c.authority_purpose in {"EXECUTABLE_QUOTE", "CONTRACT_TERMS"}
    )


def test_independent_history_and_context_require_explicit_configuration():
    sources = [
        source(
            "DUKASCOPY",
            ["candles.read"],
            configuration={
                "symbol_map": {
                    "EUR/USD": {"symbol": "EURUSD", "price_scale": "100000"},
                    "XAUUSD": {"symbol": "XAUUSD"},
                }
            },
        ),
        source(
            "CCXT",
            ["candles.read", "FUNDING"],
            configuration={
                "symbol_map": {"BTCUSD": {"symbol": "BTC/USDT:USDT"}},
            },
        ),
        source(
            "CFTC",
            ["OPEN_INTEREST"],
            configuration={
                "contracts": {
                    "EUR/USD": {"code": "099741", "report": "TFF", "categories": {"leveraged": []}},
                }
            },
        ),
        source("FRED", ["macro.read"], configuration={"series": ["DGS10"]}),
        source("ECB", ["macro.read"]),
        source("YAHOO_FINANCE", ["candles.read"], configuration={"proxies": {"vix": "^VIX"}}),
    ]
    options, _ = binding_candidates(
        {}, [lane("FOREX"), lane("METALS"), lane("CRYPTOCURRENCY")], sources, []
    )
    assert [
        (c.lane["asset_class"], c.authority_purpose) for c in options if c.provider == "DUKASCOPY"
    ] == [("FOREX", "HISTORY")]
    assert all(c.lane["asset_class"] == "CRYPTOCURRENCY" for c in options if c.provider == "CCXT")
    assert all(
        c.authority_purpose == "REFERENCE"
        for c in options
        if c.provider in {"CFTC", "YAHOO_FINANCE"}
    )
    macro = [c for c in options if c.capability == "MACROECONOMIC"]
    assert len(macro) == 1 and macro[0].lane is None and macro[0].provider == "FRED"
    assert all(c.capability != "DISCOVERY" for c in options)


def test_bridge_account_reference_mismatch_is_excluded():
    bridge = source("MT5_BRIDGE", ["market.discovery"], configuration={"account_reference": "123"})
    options, gaps = binding_candidates(
        {"broker_account_reference": "456"}, [lane("METALS")], [bridge], []
    )
    assert options == [] and gaps[0]["lane"] == "METALS:CFD"


def test_macro_sources_keep_complementary_configured_series_without_exposing_private_fields():
    sources = [
        source(
            "FRED",
            ["macro.read"],
            configuration={
                "series": ["DGS10"],
                "api_key": "private-key",
                "base_url": "https://private",
            },
        ),
        source(
            "ECB",
            ["macro.read"],
            configuration={"series": [{"flow": "EXR", "key": "D.USD.EUR.SP00.A"}]},
        ),
        source("ECB", ["macro.read"], configuration={"series": "invalid-series-format"}),
        source("CCXT", ["candles.read"], configuration={"symbol_map": "invalid-mapping-format"}),
    ]
    options, _ = binding_candidates({}, [lane("FOREX"), lane("CRYPTOCURRENCY")], sources, [])
    selected = select_candidates(options)
    assert {c.provider for c in selected} == {"FRED", "ECB"}
    assert [c.configured_coverage for c in selected] == [["DGS10"], ["EXR:D.USD.EUR.SP00.A"]]
    assert "private-key" not in str(selected) and "https://private" not in str(selected)


def test_existing_verified_binding_and_tested_sources_take_precedence_over_ai():
    existing = source("TWELVE_DATA", ["market.discovery", "candles.read"])
    native = source("MT5_BRIDGE", ["market.discovery", "candles.read"])
    untested = source("TWELVE_DATA", [], health="UNTESTED")
    binding = {
        "id": str(uuid4()),
        "state": "ACTIVE",
        "lane": {"asset_class": "FOREX", "instrument_type": "CFD"},
        "capability": "DISCOVERY",
        "authority_purpose": "DISCOVERY",
        "connection_id": existing["id"],
        "verification_status": "VERIFIED",
        "priority": 2,
    }
    options, _ = binding_candidates({}, [lane("FOREX")], [existing, native, untested], [binding])
    baseline = select_candidates(options)
    discovery = next(c for c in baseline if c.capability == "DISCOVERY")
    assert discovery.existing_binding_id == binding["id"] and discovery.status == "ALREADY_BOUND"
    advice = BindingAdvice(
        choices=[BindingChoice(candidate_id=c.candidate_id, reason="Evidence") for c in baseline]
    )
    advice.choices[0] = BindingChoice(
        candidate_id=next(
            c.candidate_id
            for c in options
            if c.provider == "MT5_BRIDGE" and c.capability == "DISCOVERY"
        ),
        reason="Prefer native",
    )
    assert (
        next(
            c for c in select_candidates(options, advice) if c.capability == "DISCOVERY"
        ).connection_id
        == existing["id"]
    )
    history_index = next(i for i, c in enumerate(baseline) if c.capability == "CANDLES")
    advice.choices[history_index] = BindingChoice(
        candidate_id=next(
            c.candidate_id
            for c in options
            if c.connection_id == untested["id"] and c.capability == "CANDLES"
        ),
        reason="Prefer untested",
    )
    with pytest.raises(ValueError, match="untested option"):
        select_candidates(options, advice)


def test_ai_cannot_invent_options_duplicate_slots_or_leave_slots_uncovered():
    options, _ = binding_candidates(
        {}, [lane("CRYPTOCURRENCY")], [source("COINBASE", ["crypto.discovery", "candles.read"])], []
    )
    with pytest.raises(ValueError, match="unknown"):
        select_candidates(
            options,
            BindingAdvice(choices=[BindingChoice(candidate_id="invented", reason="Unsupported")]),
        )
    choice = BindingChoice(candidate_id=options[0].candidate_id, reason="Supported")
    with pytest.raises(ValueError, match="duplicate"):
        select_candidates(options, BindingAdvice(choices=[choice, choice]))
    with pytest.raises(ValueError, match="every candidate slot"):
        select_candidates(options, BindingAdvice(choices=[choice]))
