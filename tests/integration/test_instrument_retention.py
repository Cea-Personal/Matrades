from sqlalchemy import ForeignKeyConstraint

from traderx.instruments.reactivation_service import begin_reactivation
from traderx.shared.db import Base, load_model_metadata
from traderx.strategies.staleness import EvidenceFreshness, RevalidationPlan


def test_replacement_reactivation_preserves_evidence_and_never_autoactivates() -> None:
    outcome = begin_reactivation(
        RevalidationPlan(EvidenceFreshness.CURRENT, ()),
        preserved_knowledge={"strategies": 2, "journal_entries": 8},
    )
    assert outcome.state == "AWAITING_HUMAN_APPROVAL"
    assert outcome.preserved_knowledge == {"strategies": 2, "journal_entries": 8}
    assert outcome.automatically_activated is False


def test_instrument_evidence_foreign_keys_never_cascade_delete() -> None:
    load_model_metadata()
    evidence_tables = {
        "instrument_aliases",
        "market_observations",
        "data_quality_observations",
        "candidate_assessments",
        "active_market_assignments",
        "strategies",
        "journal_entries",
    }
    for table_name in evidence_tables:
        table = Base.metadata.tables[table_name]
        instrument_keys = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and any(element.target_fullname == "instruments.id" for element in constraint.elements)
        ]
        assert instrument_keys, f"{table_name} must retain its instrument reference"
        assert all(key.ondelete not in {"CASCADE", "SET NULL"} for key in instrument_keys)
