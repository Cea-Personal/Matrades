from enum import StrEnum


class RecordAuthority(StrEnum):
    STRUCTURED = "STRUCTURED"
    CONTEXT_ONLY = "CONTEXT_ONLY"


AUTHORITATIVE_TYPES = {
    "account",
    "market_observation",
    "policy",
    "risk_result",
    "performance",
    "strategy_fingerprint",
}


def route(record_type: str) -> RecordAuthority:
    return (
        RecordAuthority.STRUCTURED
        if record_type in AUTHORITATIVE_TYPES
        else RecordAuthority.CONTEXT_ONLY
    )


def knowledge_envelope(hits: list) -> dict:
    return {
        "authority": "CONTEXT_ONLY",
        "citations": [hit.model_dump(mode="json") for hit in hits],
        "may_replace_facts": False,
    }
