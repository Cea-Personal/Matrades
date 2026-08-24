from enum import StrEnum


class IdentityAction(StrEnum):
    DUPLICATE = "DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    VARIANT = "VARIANT"
    NEW_VERSION = "NEW_VERSION"
    NEW_STRATEGY = "NEW_STRATEGY"


def classify(exact: bool, structural: float, same_strategy: bool = False) -> IdentityAction:
    if exact:
        return IdentityAction.DUPLICATE
    if same_strategy:
        return IdentityAction.NEW_VERSION
    if structural >= 0.9:
        return IdentityAction.NEAR_DUPLICATE
    if structural >= 0.6:
        return IdentityAction.VARIANT
    return IdentityAction.NEW_STRATEGY
