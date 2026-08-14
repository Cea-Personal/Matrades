from decimal import Decimal

from traderx.validation.monte_carlo import (
    BootstrapMode,
    bootstrap_terminal_pnls,
    stressed_bootstrap,
)
from traderx.validation.out_of_sample import chronological_split, rolling_walk_forward
from traderx.validation.stability import assess_parameter_stability, neighborhood_trials


def test_validation_artifacts_are_seeded_and_chronological() -> None:
    assert chronological_split(list(range(10))).out_of_sample == [8, 9]
    assert bootstrap_terminal_pnls(
        [Decimal("1"), Decimal("-1")], trials=3, seed=7
    ) == bootstrap_terminal_pnls([Decimal("1"), Decimal("-1")], trials=3, seed=7)
    assert (
        assess_parameter_stability([Decimal("1"), Decimal("1.1"), Decimal(".9")]).classification
        == "STABLE"
    )


def test_walk_forward_parameter_neighborhood_and_stressed_bootstraps_are_reproducible() -> None:
    assert len(
        rolling_walk_forward(
            list(range(20)), training_size=8, validation_size=4, out_of_sample_size=4, step=4
        )
    ) == 2
    assert len(neighborhood_trials(Decimal("10"))) == 5
    arguments = {
        "trials": 10,
        "seed": 42,
        "mode": BootstrapMode.BLOCK,
        "block_size": 2,
        "cost_stress": Decimal("0.01"),
        "gap_stress": Decimal("0.1"),
    }
    values = [Decimal("1"), Decimal("-0.5"), Decimal("0.25")]
    assert stressed_bootstrap(values, **arguments) == stressed_bootstrap(values, **arguments)
