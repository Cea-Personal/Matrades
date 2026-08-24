from uuid import UUID

from modules.strategies.models import StrategyDraft
from packages.strategy_sdk.taxonomy import StrategyOrigin


class DraftRepository:
    def __init__(self) -> None:
        self.items = {}

    def create(
        self, owner_id: UUID, origin: StrategyOrigin, input_text: str | None = None
    ) -> StrategyDraft:
        item = StrategyDraft(owner_id=owner_id, origin=origin, input_text=input_text)
        self.items[item.id] = item
        return item

    def save(self, draft: StrategyDraft) -> StrategyDraft:
        updated = draft.model_copy(update={"revision": draft.revision + 1})
        self.items[draft.id] = updated
        return updated
