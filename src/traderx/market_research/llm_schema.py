from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROMPT_TEMPLATE_VERSION = "independent-market-advisory-v2"
OUTPUT_SCHEMA_VERSION = "independent-market-advisory-v2"
INFERENCE_POLICY_VERSION = "bounded-no-tools-v1"


class MarketAdvisoryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(
        min_length=1,
        max_length=2000,
        description="Independent market thesis grounded only in the supplied integration evidence.",
    )
    # OpenAI-compatible strict JSON schemas require every property to be listed
    # in `required`.  The model must return empty arrays when no item applies.
    anomalies: list[str] = Field(max_length=20)
    cautions: list[str] = Field(max_length=20)
    method_proposals: list[str] = Field(
        max_length=20,
        description="Independent research hypotheses or follow-up checks; never trading instructions.",
    )


_PROHIBITED_EVIDENCE_KEYS = {
    "account",
    "account_id",
    "account_number",
    "balance",
    "credential",
    "equity",
    "login",
    "password",
    "position",
    "positions",
    "secret",
    "token",
}


def minimized_prompt_evidence(evidence: dict[str, object]) -> dict[str, object]:
    """Return normalized research facts while excluding account and credential data."""

    return {
        key: _sanitize(value)
        for key, value in sorted(evidence.items())
        if key.lower() not in _PROHIBITED_EVIDENCE_KEYS
    }


def validate_advisory_analysis(value: object) -> dict[str, object]:
    validated = MarketAdvisoryAnalysis.model_validate(value)
    return validated.model_dump(mode="json")


def advisory_json_schema() -> dict[str, Any]:
    return MarketAdvisoryAnalysis.model_json_schema()


def _sanitize(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).lower() not in _PROHIBITED_EVIDENCE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
