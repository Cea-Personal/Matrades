from uuid import uuid4

import pytest

from modules.knowledge.assistant import KnowledgeAssistant, KnowledgeQuestion
from modules.knowledge.authority import knowledge_envelope, reject_as_market_authority
from modules.knowledge.models import RetrievalHit


def test_semantic_answers_are_context_only_and_cannot_be_risk_authority() -> None:
    hit = RetrievalHit(
        document_id=uuid4(),
        segment_id=uuid4(),
        source_id=uuid4(),
        text="A trend setup needs confirmation.",
        score=1.0,
        provenance={"source": "test"},
    )
    result = KnowledgeAssistant().answer(
        KnowledgeQuestion(owner_id=uuid4(), question="what does this setup mean?"),
        [hit],
    )
    assert result.authority == "CONTEXT_ONLY"
    envelope = knowledge_envelope([hit])
    assert envelope["may_replace_facts"] is False
    with pytest.raises(ValueError, match="cannot replace"):
        reject_as_market_authority({"risk_result": {"decision": "PASS"}})
