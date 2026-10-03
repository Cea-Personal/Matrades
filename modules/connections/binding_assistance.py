"""Account-scoped binding candidates constrained by the installed research adapters."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from modules.connections.capabilities import supports_capability


class BindingChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    reason: str = Field(min_length=1, max_length=600)


class BindingAdvice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choices: list[BindingChoice] = Field(max_length=100)


class BindingCandidate(BaseModel):
    candidate_id: str
    slot: str
    binding_scope: Literal["MARKET_RESEARCH", "ECONOMIC_CONTEXT"]
    lane: dict[str, str] | None
    capability: str
    authority_purpose: str
    connection_id: str
    connection_name: str
    provider: str
    priority: int
    status: Literal["READY", "NEEDS_TEST", "ALREADY_BOUND"]
    existing_binding_id: str | None = None
    reason: str
    notes: list[str] = Field(default_factory=list)
    configured_coverage: list[str] = Field(default_factory=list)
    tested_at: str | None = None
    preference: int = 0

    def binding_payload(self) -> dict[str, Any]:
        return self.model_dump(
            include={
                "binding_scope",
                "lane",
                "capability",
                "authority_purpose",
                "connection_id",
                "priority",
            }
        )


def configuration_fingerprint(
    account: dict, matrix: dict, connections: list[dict], bindings: list[dict]
) -> str:
    """Detect changed inputs without retaining or sending connection credentials to AI."""
    sources = {
        "account": [account["id"], account["version"]],
        "matrix": matrix,
        "connections": sorted([(c["id"], c["version"], c["state"]) for c in connections]),
        "bindings": sorted([(b["id"], b["version"], b["state"]) for b in bindings]),
    }
    return sha256(json.dumps(sources, sort_keys=True, default=str).encode()).hexdigest()


def _mapped_asset(symbol: str) -> str:
    text = re.sub(r"[^A-Z]", "", symbol.upper())
    if any(token in text for token in ("XAU", "XAG", "GOLD", "SILVER")):
        return "METALS"
    fiat = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
    if text[:3] in fiat and text[3:6] in fiat:
        return "FOREX"
    return "UNKNOWN"


def _configured_coverage(connection: dict) -> list[str]:
    """Expose bounded semantic configuration, excluding secrets and network addresses."""
    config = connection.get("configuration", {})
    provider = connection["provider"]
    if provider in {"FRED", "ECB"}:
        series = config.get("series", [])
        if not isinstance(series, list):
            return []
        return [
            item[:120] if isinstance(item, str) else f"{item['flow']}:{item['key']}"[:120]
            for item in series[:12]
            if (provider == "FRED" and isinstance(item, str) and item.strip())
            or (
                provider == "ECB"
                and isinstance(item, dict)
                and item.get("flow")
                and item.get("key")
            )
        ]
    if provider in {"DUKASCOPY", "CCXT"}:
        mapping = config.get("symbol_map", {})
        if isinstance(mapping, dict):
            return [
                f"{symbol} → {terms['symbol']}"[:120]
                for symbol, terms in list(mapping.items())[:12]
                if isinstance(terms, dict) and terms.get("symbol")
            ]
    if provider == "CFTC":
        contracts = config.get("contracts", {})
        if isinstance(contracts, dict):
            return [
                f"{symbol}: {terms.get('report', '')}/{terms.get('code', '')}"[:120]
                for symbol, terms in list(contracts.items())[:12]
                if isinstance(terms, dict)
            ]
    if provider == "YAHOO_FINANCE" and isinstance(config.get("proxies"), dict):
        return [f"{name}: {symbol}"[:120] for name, symbol in list(config["proxies"].items())[:12]]
    return []


def binding_candidates(
    account: dict, lanes: list[dict], connections: list[dict], bindings: list[dict]
) -> tuple[list[BindingCandidate], list[dict[str, str]]]:
    """Build options from actual runtime coverage, never from the model's provider guesses."""
    candidates: list[BindingCandidate] = []
    gaps: list[dict[str, str]] = []
    enabled = [lane for lane in lanes if lane.get("enabled", True)]
    active = [c for c in connections if c["state"] != "DELETED" and c.get("active", True)]

    def add(
        connection: dict,
        lane: dict | None,
        capability: str,
        purpose: str,
        reason: str,
        preference: int = 0,
        notes: list[str] | None = None,
    ) -> None:
        lane = {key: lane[key] for key in ("asset_class", "instrument_type")} if lane else None
        scope: Literal["MARKET_RESEARCH", "ECONOMIC_CONTEXT"] = (
            "MARKET_RESEARCH" if lane else "ECONOMIC_CONTEXT"
        )
        coverage = f"{lane['asset_class']}:{lane['instrument_type']}" if lane else scope
        slot = f"{coverage}:{capability}:{purpose}"
        if scope == "ECONOMIC_CONTEXT" and capability == "MACROECONOMIC":
            # Regional macro sources can complement each other; choose one connection per provider.
            slot += f":{connection['provider']}"
        candidate_id = sha256(f"{slot}:{connection['id']}".encode()).hexdigest()[:24]
        tested = connection.get("health") == "HEALTHY" and supports_capability(
            connection.get("capabilities", []), capability
        )
        existing = next(
            (
                b
                for b in bindings
                if b["state"] != "DELETED"
                and b.get("binding_scope", "MARKET_RESEARCH") == scope
                and b.get("lane") == lane
                and b.get("capability") == capability
                and b.get("authority_purpose") == purpose
                and b.get("connection_id") == connection["id"]
            ),
            None,
        )
        covered = bool(tested and existing and existing.get("verification_status") == "VERIFIED")
        candidates.append(
            BindingCandidate(
                candidate_id=candidate_id,
                slot=slot,
                binding_scope=scope,
                lane=lane,
                capability=capability,
                authority_purpose=purpose,
                connection_id=connection["id"],
                connection_name=str(connection.get("name", connection["provider"])),
                provider=connection["provider"],
                priority=int(existing.get("priority", 1)) if existing else 1,
                status="ALREADY_BOUND" if covered else "READY" if tested else "NEEDS_TEST",
                existing_binding_id=existing["id"] if existing else None,
                reason=reason,
                configured_coverage=_configured_coverage(connection),
                tested_at=connection.get("last_checked"),
                notes=(notes or [])
                + (
                    []
                    if tested
                    else ["Test this connection for the required capability before verification."]
                ),
                preference=preference,
            )
        )

    for lane in enabled:
        asset, kind = lane["asset_class"], lane["instrument_type"]
        lane_key = f"{asset}:{kind}"
        for connection in active:
            provider, config = connection["provider"], connection.get("configuration", {})
            if kind in {"SPOT", "CFD"}:
                if provider == "MT5_BRIDGE" and kind == "CFD" and asset in {"FOREX", "METALS"}:
                    account_ref = str(account.get("broker_account_reference") or "").strip()
                    bridge_ref = str(config.get("account_reference") or "").strip()
                    if account_ref and account_ref != bridge_ref:
                        continue
                    notes = [
                        "The EA's InpMatradesAccountId must match this account's ID. "
                        "Connection testing does not verify that account mapping."
                    ]
                    add(
                        connection,
                        lane,
                        "DISCOVERY",
                        "DISCOVERY",
                        "Broker-native CFD symbols, quotes and candles for this lane.",
                        0,
                        notes,
                    )
                    add(
                        connection,
                        lane,
                        "CANDLES",
                        "HISTORY",
                        "Keep broker history aligned with the researched CFD instrument.",
                        10,
                        notes,
                    )
                    add(
                        connection,
                        lane,
                        "QUOTE",
                        "EXECUTABLE_QUOTE",
                        "Use broker bid/ask prices for executable CFD price checks.",
                        0,
                        notes,
                    )
                    add(
                        connection,
                        lane,
                        "CONTRACT_DETAILS",
                        "CONTRACT_TERMS",
                        "Broker lot steps, tick values and contract sizes support position sizing.",
                        0,
                        notes,
                    )
                elif provider == "TWELVE_DATA" and asset in {"FOREX", "STOCKS"}:
                    notes = (
                        ["CFD research is a market proxy; execution needs broker prices and terms."]
                        if kind == "CFD"
                        else []
                    )
                    add(
                        connection,
                        lane,
                        "DISCOVERY",
                        "DISCOVERY",
                        "Supported instrument discovery, quotes and H1 history for this lane.",
                        10,
                        notes,
                    )
                    add(
                        connection,
                        lane,
                        "CANDLES",
                        "HISTORY",
                        "Native research history from the selected market data provider.",
                        10,
                        notes,
                    )
                elif provider == "COINBASE" and asset == "CRYPTOCURRENCY":
                    notes = (
                        ["Spot crypto is a CFD proxy; execution requires broker validation."]
                        if kind == "CFD"
                        else []
                    )
                    add(
                        connection,
                        lane,
                        "DISCOVERY",
                        "DISCOVERY",
                        "Supported cryptocurrency discovery and price history.",
                        0,
                        notes,
                    )
                    add(
                        connection,
                        lane,
                        "CANDLES",
                        "HISTORY",
                        "Keep crypto research history on the same Coinbase venue.",
                        10,
                        notes,
                    )
                elif provider == "DUKASCOPY" and asset in {"FOREX", "METALS"}:
                    mapping = config.get("symbol_map", {})
                    mapped = (
                        [
                            key
                            for key, value in mapping.items()
                            if isinstance(value, dict)
                            and value.get("symbol")
                            and value.get("price_scale")
                            and _mapped_asset(key) == asset
                        ]
                        if isinstance(mapping, dict)
                        else []
                    )
                    if mapped:
                        add(
                            connection,
                            lane,
                            "CANDLES",
                            "HISTORY",
                            "Independent bid/ask history with explicit symbol and scale mappings.",
                            0,
                            ["Only mapped instruments are covered; verify each price scale."],
                        )
                elif (
                    provider == "CCXT"
                    and asset == "CRYPTOCURRENCY"
                    and _configured_coverage(connection)
                ):
                    add(
                        connection,
                        lane,
                        "CANDLES",
                        "HISTORY",
                        "Independent public exchange history with explicit instrument mappings.",
                        0,
                        ["Check the symbol mapping across spot, perpetual and broker CFD markets."],
                    )
                    for capability in ("FUNDING", "OPEN_INTEREST", "ORDER_BOOK", "TRADES"):
                        if supports_capability(connection.get("capabilities", []), capability):
                            add(
                                connection,
                                lane,
                                capability,
                                "REFERENCE",
                                "Public exchange context from an advertised capability.",
                            )
            if provider == "CFTC" and asset in {"FOREX", "METALS", "STOCKS"}:
                contracts = config.get("contracts", {})
                if isinstance(contracts, dict) and any(
                    isinstance(m, dict)
                    and m.get("code")
                    and m.get("report")
                    and m.get("categories")
                    for m in contracts.values()
                ):
                    add(
                        connection,
                        lane,
                        "OPEN_INTEREST",
                        "REFERENCE",
                        "Configured COT futures positioning provides reference context.",
                        notes=[
                            "Coverage is limited to the explicit contract/report/category mappings."
                        ],
                    )
            elif provider == "YAHOO_FINANCE" and _configured_coverage(connection):
                add(
                    connection,
                    lane,
                    "CANDLES",
                    "REFERENCE",
                    "Named intermarket proxies add context without replacing pair history.",
                )
        if not any(
            c.lane
            and c.lane == {key: lane[key] for key in ("asset_class", "instrument_type")}
            and c.capability == "DISCOVERY"
            for c in candidates
        ):
            message = "No configured source supports discovery for this lane."
            if kind == "FUTURES":
                message = (
                    "The connected research workflow has no futures discovery adapter; "
                    "spot/CFD sources cannot fill this lane."
                )
            elif asset == "METALS" and kind == "CFD":
                message = (
                    "Configure an MT5 Bridge for Metals CFD research; "
                    "independent history cannot replace broker discovery."
                )
            gaps.append({"lane": lane_key, "reason": message})

    if enabled:
        for connection in active:
            provider, config = connection["provider"], connection.get("configuration", {})
            if provider in {"FOREX_FACTORY", "CALENDAR"}:
                add(
                    connection,
                    None,
                    "ECONOMIC_CALENDAR",
                    "REFERENCE",
                    "Account calendar context helps identify event risk across enabled lanes.",
                    0 if provider == "FOREX_FACTORY" else 10,
                )
            elif provider in {"FRED", "ECB"} and _configured_coverage(connection):
                add(
                    connection,
                    None,
                    "MACROECONOMIC",
                    "REFERENCE",
                    "Explicitly configured macro series provide account research context.",
                )
            elif provider == "NEWS":
                add(
                    connection,
                    None,
                    "NEWS",
                    "REFERENCE",
                    "Configured news provides account context with its own freshness checks.",
                )
    return candidates, gaps


def select_candidates(
    candidates: list[BindingCandidate], advice: BindingAdvice | None = None
) -> list[BindingCandidate]:
    """AI may choose compatible options; it cannot invent or alter a binding payload."""
    by_slot: dict[str, list[BindingCandidate]] = {}
    for candidate in candidates:
        by_slot.setdefault(candidate.slot, []).append(candidate)
    selected = {}
    for slot, options in by_slot.items():
        selected[slot] = min(
            options,
            key=lambda c: (
                {"ALREADY_BOUND": 0, "READY": 1, "NEEDS_TEST": 2}[c.status],
                c.priority if c.status == "ALREADY_BOUND" else c.preference,
                c.connection_id,
            ),
        )
    if advice is not None:
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        seen = set()
        for choice in advice.choices:
            option = by_id.get(choice.candidate_id)
            if option is None or option.slot in seen:
                raise ValueError("AI chose an unknown or duplicate binding option")
            seen.add(option.slot)
            current = selected[option.slot]
            if current.status == "ALREADY_BOUND":
                continue
            if current.status == "READY" and option.status == "NEEDS_TEST":
                raise ValueError("AI chose an untested option over a tested compatible source")
            selected[option.slot] = option.model_copy(update={"reason": choice.reason})
        if seen != set(by_slot):
            raise ValueError("AI did not cover every candidate slot")
    return list(selected.values())
