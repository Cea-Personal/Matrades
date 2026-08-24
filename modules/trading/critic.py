from dataclasses import dataclass


@dataclass(frozen=True)
class CriticResult:
    accepted: bool
    explanation: str


def conservative_critic(output: dict[str, object] | None) -> CriticResult:
    if (
        not output
        or not isinstance(output.get("accepted"), bool)
        or not isinstance(output.get("explanation"), str)
    ):
        return CriticResult(False, "critic unavailable or returned an invalid schema")
    return CriticResult(bool(output["accepted"]), str(output["explanation"]))
