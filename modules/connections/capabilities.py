"""Capability names shared by binding verification and configuration assistance."""

CAPABILITY_ALIASES: dict[str, set[str]] = {
    "DISCOVERY": {
        "DISCOVERY",
        "MARKET.DISCOVERY",
        "INSTRUMENT_DIRECTORY",
        "INSTRUMENT_DIRECTORY.READ",
        "INSTRUMENTS.READ",
        "CRYPTO.DISCOVERY",
        "ASSET_METADATA.READ",
    },
    "INSTRUMENT_DIRECTORY": {
        "DISCOVERY",
        "MARKET.DISCOVERY",
        "INSTRUMENT_DIRECTORY",
        "INSTRUMENT_DIRECTORY.READ",
        "INSTRUMENTS.READ",
    },
    "QUOTE": {"QUOTE", "QUOTES", "QUOTES.READ", "FOREX.READ", "METALS.READ", "CRYPTO.READ"},
    "CANDLES": {"CANDLE", "CANDLES", "HISTORY", "CANDLES.READ", "HISTORY.READ"},
    "FUTURES_CHAIN": {"FUTURES_CHAIN", "CONTRACT_DETAILS"},
    "CONTRACT_DETAILS": {"CONTRACT_DETAILS", "CONTRACT_TERMS.READ", "FUTURES_CHAIN"},
    "OPEN_INTEREST": {"OPEN_INTEREST", "OPEN_INTEREST.READ", "CFTC_COT"},
    "FUNDING": {"FUNDING", "FUNDING.READ"},
    "ORDER_BOOK": {"ORDER_BOOK", "ORDER_BOOK.READ"},
    "TRADES": {"TRADES", "TRADES.READ"},
    "ECONOMIC_CALENDAR": {
        "ECONOMIC_CALENDAR",
        "CALENDAR",
        "NEWS",
        "CALENDAR.READ",
        "NEWS.READ",
        "FOREX_FACTORY.SCRAPE",
    },
    "MACROECONOMIC": {"MACROECONOMIC", "MACRO", "ECONOMIC", "MACRO.READ"},
    "NEWS": {"NEWS", "NEWS.READ", "SEARCH.READ"},
}


def supports_capability(advertised: list[str], required: str) -> bool:
    return bool(
        {str(item).upper() for item in advertised}
        & CAPABILITY_ALIASES.get(required.upper(), {required.upper()})
    )
