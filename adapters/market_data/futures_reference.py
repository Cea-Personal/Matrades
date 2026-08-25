"""Provider-neutral exact futures-chain/reference adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from adapters.base import AdapterCapability


class FuturesReference(Protocol):
    async def chain(self, underlying: str, as_of: datetime) -> list[dict[str, Any]]: ...

    async def contract_details(self, contract: str, as_of: datetime) -> dict[str, Any]: ...


class FuturesReferenceAdapter:
    CAPABILITIES = frozenset(
        {
            AdapterCapability.FUTURES_CHAIN,
            AdapterCapability.CONTRACT_DETAILS,
            AdapterCapability.OPEN_INTEREST,
        }
    )

    def __init__(self, reference: FuturesReference) -> None:
        self.reference = reference

    def capabilities(self) -> set[str]:
        return {item.value for item in self.CAPABILITIES}

    async def futures_chain(self, underlying: str, as_of: datetime) -> list[dict[str, Any]]:
        return await self.reference.chain(underlying, as_of)

    async def contract_details(self, contract: str, as_of: datetime) -> dict[str, Any]:
        return await self.reference.contract_details(contract, as_of)
