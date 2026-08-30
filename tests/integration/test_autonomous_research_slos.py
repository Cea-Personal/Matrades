from modules.research.matrix import ALL_LANES


def test_research_matrix_is_bounded_to_twelve_lanes() -> None:
    assert len(ALL_LANES) == 12
