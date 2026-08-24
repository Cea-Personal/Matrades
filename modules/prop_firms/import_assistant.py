from modules.prop_firms.models import PropRule, RuleSet


def preview(program_id, payload: dict, version: int) -> RuleSet:
    rules = [PropRule.model_validate(item) for item in payload.get("rules", [])]
    return RuleSet(
        program_id=program_id, version=version, rules=rules, source_reference=payload.get("source")
    )
