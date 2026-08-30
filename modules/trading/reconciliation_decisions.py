from modules.trading.broker_models import Reconciliation, ReconciliationState
from modules.trading.models import OutcomeCertainty, ReconciliationRecord


def resolve(reconciliation: Reconciliation, position_id: str) -> Reconciliation:
    if (
        reconciliation.state != ReconciliationState.AMBIGUOUS
        or position_id not in reconciliation.candidate_position_ids
    ):
        raise ValueError("position is not an ambiguous candidate")
    return reconciliation.model_copy(
        update={"state": ReconciliationState.MATCHED, "selected_position_id": position_id}
    )


def retry_allowed(reconciliation: ReconciliationRecord) -> bool:
    """Retries are allowed only after a confirmed no-effect reconciliation."""
    return (
        reconciliation.state == "NO_EFFECT_CONFIRMED"
        and reconciliation.certainty is OutcomeCertainty.CONFIRMED
    )
