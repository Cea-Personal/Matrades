from decimal import Decimal

from traderx.validation.monte_carlo import bootstrap_terminal_pnls
from traderx.validation.out_of_sample import chronological_split
from traderx.validation.stability import assess_parameter_stability


def test_validation_artifacts_are_seeded_and_chronological() -> None:
    assert chronological_split(list(range(10))).out_of_sample == [8, 9]
    assert bootstrap_terminal_pnls(
        [Decimal("1"), Decimal("-1")], trials=3, seed=7
    ) == bootstrap_terminal_pnls([Decimal("1"), Decimal("-1")], trials=3, seed=7)
    assert (
        assess_parameter_stability([Decimal("1"), Decimal("1.1"), Decimal(".9")]).classification
        == "STABLE"
    )
