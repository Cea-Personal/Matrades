from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.market_data.models import InstrumentSpecificationVersion
from modules.risk.live_terms import load_live_trade_terms
from packages.shared.domain_types import InstrumentType, QuantityUnit
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.mark.parametrize(
    "price_currency,authority,error",
    [
        ("USD", "MT5_BROKER", None),
        ("JPY", "MT5_BROKER", "account-currency conversion"),
        ("USD", "MT5_BROKER_VALIDATION_REQUIRED", "broker-native CFD terms"),
    ],
)
async def test_live_terms_are_account_scoped_and_never_use_a_research_proxy(
    price_currency: str, authority: str, error: str | None
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid4()
    account_id = uuid4()
    listing_id = uuid4()
    specification = InstrumentSpecificationVersion(
        venue_instrument_id=listing_id,
        effective_from=datetime.now(UTC),
        price_currency=price_currency,
        quantity_unit=QuantityUnit.LOTS,
        contract_multiplier=Decimal("100"),
        quantity_minimum=Decimal("0.01"),
        quantity_maximum=Decimal("20"),
        quantity_step=Decimal("0.01"),
        provenance={"provider": "mt5_bridge", "execution_authority": authority},
    )
    try:
        async with factory() as session, session.begin():
            store = ResourceStore(session)
            await store.create(
                "account",
                owner_id,
                {"name": "test", "currency": "USD", "starting_balance": "10000"},
                record_id=account_id,
                state="ACTIVE",
            )
            await store.create(
                "typed_instrument",
                owner_id,
                {
                    "account_id": str(account_id),
                    "specification_version_id": str(specification.id),
                    "quantity_unit": "LOTS",
                    "listing": {"executable": True},
                    "specification": specification.model_dump(mode="json"),
                },
            )
            if error:
                with pytest.raises(ValueError, match=error):
                    await load_live_trade_terms(
                        session,
                        owner_id,
                        account_id,
                        listing_id,
                        specification.id,
                        InstrumentType.CFD,
                    )
            else:
                terms = await load_live_trade_terms(
                    session,
                    owner_id,
                    account_id,
                    listing_id,
                    specification.id,
                    InstrumentType.CFD,
                )
                assert terms.contract_multiplier == 100
                assert terms.quantity_maximum == 20
            with pytest.raises(ValueError, match="account-scoped"):
                await load_live_trade_terms(
                    session,
                    owner_id,
                    account_id,
                    listing_id,
                    uuid4(),
                    InstrumentType.CFD,
                )
    finally:
        await engine.dispose()
