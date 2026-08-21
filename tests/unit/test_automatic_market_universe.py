from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.integrations.model import Integration
from traderx.market_data.model import Instrument, InstrumentAlias
from traderx.market_research import service
from traderx.market_research.model import CandidateAssessment, MarketResearchRun, ResearchRunState
from traderx.shared.db import Base, load_model_metadata
from traderx.shared.types import MarketCategory


def test_mt5_catalogue_excludes_currency_named_etfs_from_forex() -> None:
    assert (
        service.classify_mt5_instrument(
            {
                "symbol": "FXA",
                "path": "Nasdaq\\ETF\\FXA",
                "currency_base": "USD",
                "currency_profit": "USD",
            }
        )
        is None
    )
    assert (
        service.classify_mt5_instrument(
            {
                "symbol": "EURUSD",
                "path": "Forex\\Majors",
                "currency_base": "EUR",
                "currency_profit": "USD",
            }
        )
        == MarketCategory.FOREX
    )


def test_library_can_request_review_for_any_eligible_ranked_instrument() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        instrument = Instrument(
            symbol="ETHUSD",
            display_name="ETH / USD",
            category="CRYPTO",
            status="INACTIVE",
            contract_spec={},
            trading_hours={},
        )
        database.add(instrument)
        database.flush()
        run = MarketResearchRun(
            category="CRYPTO",
            method_version="market-suitability-v2",
            input_manifest_hash="a" * 64,
            state=ResearchRunState.COMPLETED,
            created_at=now,
            completed_at=now,
        )
        database.add(run)
        database.flush()
        assessment = CandidateAssessment(
            research_run_id=run.id,
            instrument_id=instrument.id,
            eligible=True,
            gate_evidence={"reason_codes": []},
            components={"liquidity": "0.9"},
            score=Decimal("0.8"),
            rank=2,
            confidence=Decimal("0.9"),
            explanation={},
            source_evidence=[],
        )
        database.add(assessment)
        database.flush()

        candidate = service.activation_candidate_for_instrument(
            database, instrument_id=instrument.id
        )

        assert candidate["id"] == str(assessment.id)
        assert candidate["rank"] == 2
        assert candidate["symbol"] == "ETHUSD"
def test_coinbase_catalogue_automatically_maps_active_core_usd_products(monkeypatch) -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)

    class CoinbaseCatalogue:
        def __init__(self, transport) -> None:
            del transport

        def discover_instruments(self, category: str) -> list[dict[str, object]]:
            assert category == "CRYPTO"
            return [
                {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online"},
                {"id": "ETH-USD", "base_currency": "ETH", "quote_currency": "USD", "status": "active"},
                {"id": "BTC-USDC", "base_currency": "BTC", "quote_currency": "USDC", "status": "online"},
                {"id": "NEW-USD", "base_currency": "NEW", "quote_currency": "USD", "status": "online"},
                {"id": "SOL-USD", "base_currency": "SOL", "quote_currency": "USD", "trading_disabled": True},
            ]

        def get_instrument_market_snapshot(self, provider_symbol: str) -> dict[str, object]:
            return {
                "product": {
                    "id": provider_symbol,
                    "quote_increment": "0.01",
                    "base_increment": "0.00000001",
                    "base_min_size": "0.0001",
                },
                "ticker": {"bid": "100.00", "ask": "100.01"},
                "candles": [
                    [str(1_700_000_000 + index * 3_600), "99", "101", "100", "100", "10"]
                    for index in range(61)
                ],
            }

    monkeypatch.setattr(service, "CoinbaseExchangeAdapter", CoinbaseCatalogue)
    with Session(engine) as database, database.begin():
        database.add(
            Integration(
                name="Coinbase catalogue",
                category="MARKET_DATA",
                provider="COINBASE_EXCHANGE",
                state="HEALTHY",
                capabilities=["MARKET_DATA_READ"],
                configuration={},
                official_source=True,
                catalogue_revision="2026-08-14.v1",
                adapter_revision="v1",
                entitlement_status="NOT_REQUIRED",
            )
        )
        database.flush()

        assert service.refresh_coinbase_instrument_catalog(database) == 2
        instruments = list(database.scalars(select(Instrument).order_by(Instrument.symbol)))
        aliases = list(database.scalars(select(InstrumentAlias).order_by(InstrumentAlias.native_symbol)))

        assert [instrument.symbol for instrument in instruments] == ["BTCUSD", "ETHUSD"]
        assert [alias.native_symbol for alias in aliases] == ["BTC-USD", "ETH-USD"]
        assert all(alias.approved_at is not None for alias in aliases)
        assert all(alias.provider_metadata["automatic_universe"] is True for alias in aliases)
        inputs, _, _ = service._research_inputs(instruments[0])
        assert inputs.data_verified is True
        assert inputs.sizing_supported is True
        assert inputs.hours_supported is True
        assert inputs.gap_risk_acceptable is True
