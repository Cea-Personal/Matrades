"""Account-bound public positioning, macro, derivatives and intermarket evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from adapters.macro.providers import CftcProvider, FredProvider, positioning_features
from adapters.market_data.public_research import crypto_context, ecb_series, yahoo_history
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import resolve_connection
from modules.market_data.research_history import configuration_hash
from modules.market_data.research_store import ResearchDataStore
from modules.research.quantitative_features import candle_frame
from packages.shared.config import settings
from packages.shared.store import ResourceStore


async def collect_context(
    db, owner_id: UUID, account_id: UUID, instrument: str, start: datetime, end: datetime
) -> tuple[dict, dict]:
    store = ResourceStore(db)
    archive = ResearchDataStore(settings.research_data_root, owner_id)
    bindings = [
        b
        for b in await store.list("provider_binding", owner_id)
        if b.data.get("account_id") == str(account_id)
        and b.data.get("authority_purpose") == "REFERENCE"
        and b.data.get("verification_status") == "VERIFIED"
    ]
    evidence, proxies, seen = [], {}, set()
    archived_contexts = await store.list("market_context", owner_id)
    for binding in sorted(bindings, key=lambda b: (int(b.data.get("priority", 1)), str(b.id))):
        connection_id = UUID(binding.data["connection_id"])
        if connection_id in seen:
            continue
        seen.add(connection_id)
        provider = None
        try:
            connection = await resolve_connection(db, owner_id, connection_id)
            provider, config = connection.profile.provider, connection.profile.configuration
            # A previous first-seen snapshot can inform a later discovery cutoff.
            previous = {}
            for record in archived_contexts:
                data = record.data
                if (
                    data.get("account_id") != str(account_id)
                    or data.get("instrument") != instrument
                    or data.get("connection_id") != str(connection_id)
                    or data.get("configuration_hash") != configuration_hash(connection)
                    or datetime.fromisoformat(data["available_at"]) > end
                    or data.get("provider") == "YAHOO_FINANCE"
                ):
                    continue
                topic = tuple(
                    str(data.get("summary", {}).get(key, ""))
                    for key in (
                        "flow",
                        "key",
                        "series",
                        "name",
                        "symbol",
                        "contract_code",
                        "report",
                    )
                )
                if (
                    topic not in previous
                    or data["available_at"] > previous[topic].data["available_at"]
                ):
                    previous[topic] = record
            for record in previous.values():
                # Verify archived bytes before treating stored context as evidence.
                archive.get(record.data["archive"])
                evidence.append(
                    {
                        "context_id": str(record.id),
                        "provider": provider.value,
                        "status": "AVAILABLE_ARCHIVED",
                        "available_at": record.data["available_at"],
                        "summary": record.data["summary"],
                        "visible_at_discovery_cut": True,
                        "backtest_context_eligible": False,
                        "point_in_time": record.data["point_in_time"],
                        "archive": record.data["archive"],
                    }
                )
            contexts = []
            if provider == ConnectionProvider.CFTC:
                mapping = config.get("contracts", {}).get(instrument)
                if not isinstance(mapping, dict):
                    raise ValueError(
                        "CFTC needs an exact contract/report/category mapping for this pair"
                    )
                cot_client = CftcProvider()
                try:
                    rows = await cot_client.cot(
                        str(mapping["code"]),
                        report=str(mapping["report"]),
                        weeks=int(mapping.get("weeks", 156)),
                    )
                finally:
                    await cot_client.close()
                fields = mapping.get("categories", {})
                if not fields or len(fields) > 5:
                    raise ValueError("COT mapping needs 1–5 explicit report category field pairs")
                contexts.append(
                    {
                        "provider": "CFTC",
                        "contract_code": mapping["code"],
                        "report": mapping["report"],
                        "raw": rows,
                        "categories": {
                            category: positioning_features(
                                rows, long_field=pair[0], short_field=pair[1]
                            )
                            for category, pair in fields.items()
                        },
                        "point_in_time": "FIRST_SEEN_ONLY",
                    }
                )
            elif provider == ConnectionProvider.ECB:
                if not config.get("series"):
                    raise ValueError("ECB needs explicit SDMX series flow/key configuration")
                for series in config.get("series", [])[:5]:
                    contexts.append(
                        await ecb_series(str(series["flow"]), str(series["key"]), start, end)
                    )
            elif provider == ConnectionProvider.FRED and connection.secret:
                if not config.get("series"):
                    raise ValueError("FRED needs configured series IDs")
                fred_client = FredProvider(connection.secret)
                try:
                    for series in config.get("series", [])[:5]:
                        contexts.append(
                            {
                                "provider": "FRED",
                                "series": str(series),
                                "vintage_as_of": end.date().isoformat(),
                                "data": await fred_client.series(str(series), as_of=end),
                                "point_in_time": "FIRST_SEEN_ONLY",
                            }
                        )
                finally:
                    await fred_client.close()
            elif provider == ConnectionProvider.YAHOO_FINANCE:
                if not config.get("proxies"):
                    raise ValueError("Yahoo intermarket context needs named proxies")
                for name, symbol in list(config.get("proxies", {}).items())[:5]:
                    candles, source = await yahoo_history(str(symbol), start, end, "1d")
                    frame = candle_frame(candles, 86400)
                    frame = frame[frame.index <= end]
                    proxies[str(name)] = frame.close
                    contexts.append(
                        {
                            **source,
                            "name": name,
                            "normalized": archive.frame(frame),
                            "point_in_time": "UNADJUSTED_CLOSE_PLUS_CONSERVATIVE_ONE_DAY",
                        }
                    )
            elif provider == ConnectionProvider.CCXT:
                mapping = config.get("symbol_map", {}).get(instrument)
                if isinstance(mapping, dict):
                    contexts.append(
                        await crypto_context(
                            str(config.get("exchange", "coinbase")), str(mapping["symbol"])
                        )
                    )
            else:
                continue
            for context in contexts:
                context.setdefault("available_at", datetime.now(UTC).isoformat())
                summary = {
                    key: context[key]
                    for key in (
                        "flow",
                        "key",
                        "series",
                        "name",
                        "symbol",
                        "exchange",
                        "market_type",
                        "contract_code",
                        "report",
                    )
                    if key in context
                }
                if provider == ConnectionProvider.CFTC:
                    summary["positioning"] = {
                        name: values[-1] for name, values in context["categories"].items()
                    }
                elif provider == ConnectionProvider.ECB:
                    summary["latest_observation"] = (
                        context["observations"][-1] if context["observations"] else None
                    )
                elif provider == ConnectionProvider.CCXT:
                    funding = context.get("fetchFundingRate", {})
                    interest = context.get("fetchOpenInterest", {})
                    summary.update(
                        funding_rate=funding.get("fundingRate"),
                        open_interest=interest.get("openInterestAmount"),
                        funding_timestamp=funding.get("timestamp"),
                    )
                elif provider == ConnectionProvider.FRED:
                    summary["latest_observation"] = (context["data"].get("observations") or [None])[
                        -1
                    ]
                raw = archive.json(context)
                visible = (
                    datetime.fromisoformat(context["available_at"]) <= end
                    or provider == ConnectionProvider.YAHOO_FINANCE
                )
                record = await store.create(
                    "market_context",
                    owner_id,
                    {
                        "account_id": str(account_id),
                        "instrument": instrument,
                        "connection_id": str(connection_id),
                        "binding_id": str(binding.id),
                        "provider": provider.value,
                        "configuration_hash": configuration_hash(connection),
                        "archive": raw,
                        "summary": summary,
                        "available_at": context["available_at"],
                        "execution_authority": False,
                        "point_in_time": context.get("point_in_time", "FIRST_SEEN_ONLY"),
                    },
                    event_type="research_context.archived",
                )
                evidence.append(
                    {
                        "context_id": str(record.id),
                        "provider": provider.value,
                        "status": "AVAILABLE" if visible else "WITHHELD_AFTER_DISCOVERY_CUT",
                        "available_at": context["available_at"],
                        "backtest_context_eligible": provider == ConnectionProvider.YAHOO_FINANCE,
                        "summary": summary if visible else {},
                        "visible_at_discovery_cut": visible,
                        "point_in_time": context.get("point_in_time", "FIRST_SEEN_ONLY"),
                        "archive": raw,
                    }
                )
        except Exception as exc:
            # Context failures are visible and neutral, never synthetic data.
            evidence.append(
                {
                    "provider": provider.value if provider else "UNRESOLVED",
                    "connection_id": str(connection_id),
                    "status": "UNAVAILABLE",
                    "error_type": type(exc).__name__,
                    "safe_message": str(exc)[:250]
                    if isinstance(exc, ValueError)
                    else "Public context unavailable; no synthetic or alternate venue substitution",
                }
            )
    return {
        "sources": evidence,
        "authority": "CONTEXT_ONLY",
        "execution_authorized": False,
    }, proxies
