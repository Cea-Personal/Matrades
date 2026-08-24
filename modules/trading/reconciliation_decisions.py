from modules.trading.broker_models import Reconciliation, ReconciliationState


def resolve(reconciliation: Reconciliation, position_id: str) -> Reconciliation:
    if (
        reconciliation.state != ReconciliationState.AMBIGUOUS
        or position_id not in reconciliation.candidate_position_ids
    ):
        raise ValueError("position is not an ambiguous candidate")
    return reconciliation.model_copy(
        update={"state": ReconciliationState.MATCHED, "selected_position_id": position_id}
    )
