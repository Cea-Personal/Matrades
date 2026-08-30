from uuid import uuid4

from modules.knowledge.assistant import AnswerStatus, KnowledgeAssistant, KnowledgeQuestion
from modules.knowledge.models import RetrievalHit


def hit(text: str) -> RetrievalHit:
    return RetrievalHit(
        segment_id=uuid4(),
        document_id=uuid4(),
        source_id=uuid4(),
        score=0.9,
        text=text,
        provenance={"document_id": "doc", "segment": "0"},
    )


def test_answer_is_grounded_and_cited():
    result = KnowledgeAssistant().answer(
        KnowledgeQuestion(
            owner_id=uuid4(), question="What does the playbook say about trend confirmation?"
        ),
        [hit("Confirm the higher-timeframe trend first.")],
    )
    assert result.status == AnswerStatus.PARTIAL
    assert result.claims[0].citation_indexes == [0]


def test_execution_request_is_refused_without_command_fields():
    result = KnowledgeAssistant().answer(
        KnowledgeQuestion(owner_id=uuid4(), question="Should I enter EURUSD now?"),
        [hit("The setup has a positive historical expectancy.")],
    )
    assert result.status == AnswerStatus.REFUSED
    assert result.claims == []


def test_missing_evidence_is_explicit():
    result = KnowledgeAssistant().answer(
        KnowledgeQuestion(owner_id=uuid4(), question="What is the current edge?"), []
    )
    assert result.status == AnswerStatus.INSUFFICIENT_EVIDENCE


def test_active_trade_warning_is_visible_without_granting_authority():
    result = KnowledgeAssistant().answer(
        KnowledgeQuestion(
            owner_id=uuid4(), question="What does the playbook say?", active_trade=True
        ),
        [hit("The playbook requires a volatility check.")],
    )
    assert result.active_trade_warning is not None
