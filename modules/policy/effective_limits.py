from __future__ import annotations

from collections import defaultdict

from modules.policy.models import ConstraintKind, EffectiveConstraint, Enforcement


def strictest_applicable(
    constraints: list[EffectiveConstraint],
) -> dict[ConstraintKind, EffectiveConstraint]:
    grouped: dict[ConstraintKind, list[EffectiveConstraint]] = defaultdict(list)
    for constraint in constraints:
        grouped[constraint.kind].append(constraint)
    result: dict[ConstraintKind, EffectiveConstraint] = {}
    for kind, choices in grouped.items():
        hard = [choice for choice in choices if choice.enforcement == Enforcement.HARD]
        pool = hard or choices
        result[kind] = min(pool, key=lambda item: item.value)
    return result
