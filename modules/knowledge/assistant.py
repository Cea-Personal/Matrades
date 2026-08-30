"""Grounded, read-only answers over the Matrades knowledge store.

The assistant deliberately has no execution tools.  It can explain indexed
evidence and journal context, but it cannot turn a question into a broker
command.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from modules.knowledge.models import RetrievalHit


class AnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DEGRADED = "DEGRADED"
    REFUSED = "REFUSED"


class KnowledgeQuestion(BaseModel):
    owner_id: UUID
    question: str = Field(min_length=1, max_length=4000)
    correlation_id: UUID = Field(default_factory=uuid4)
    active_trade: bool = False


class KnowledgeCitation(BaseModel):
    document_id: UUID
    segment_id: UUID
    source_id: UUID
    score: float
    provenance: dict[str, str]


class KnowledgeClaim(BaseModel):
    text: str
    citation_indexes: list[int] = Field(min_length=1)


class KnowledgeAnswer(BaseModel):
    correlation_id: UUID
    status: AnswerStatus
    answer: str
    claims: list[KnowledgeClaim] = []
    citations: list[KnowledgeCitation] = []
    authority: str = "CONTEXT_ONLY"
    refusal_reason: str | None = None
    active_trade_warning: str | None = None


_EXECUTION_WORDS = (
    "enter",
    "place order",
    "cancel",
    "modify",
    "close",
    "exit",
    "buy now",
    "sell now",
)


class KnowledgeAssistant:
    """Return answers whose claims are directly tied to retrieval hits."""

    def answer(
        self,
        question: KnowledgeQuestion,
        hits: list[RetrievalHit],
        *,
        degraded: bool = False,
    ) -> KnowledgeAnswer:
        normalized = question.question.casefold()
        if any(term in normalized for term in _EXECUTION_WORDS):
            return KnowledgeAnswer(
                correlation_id=question.correlation_id,
                status=AnswerStatus.REFUSED,
                answer="I can explain evidence, but I cannot place, change, or close trades.",
                refusal_reason="execution requests are outside the knowledge assistant scope",
                active_trade_warning=(
                    "An active trade exists; current broker state and risk authority remain "
                    "authoritative."
                    if question.active_trade
                    else None
                ),
            )
        if not hits:
            return KnowledgeAnswer(
                correlation_id=question.correlation_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer="No indexed evidence supports an answer to this question.",
                active_trade_warning=(
                    "An active trade exists; current broker state and risk authority remain "
                    "authoritative."
                    if question.active_trade
                    else None
                ),
            )

        citations = [
            KnowledgeCitation(
                document_id=hit.document_id,
                segment_id=hit.segment_id,
                source_id=hit.source_id,
                score=hit.score,
                provenance=hit.provenance,
            )
            for hit in hits
        ]
        claims = [
            KnowledgeClaim(text=hit.text, citation_indexes=[index])
            for index, hit in enumerate(hits)
        ]
        answer = "\n\n".join(f"[{index + 1}] {hit.text}" for index, hit in enumerate(hits))
        status = (
            AnswerStatus.DEGRADED
            if degraded
            else AnswerStatus.PARTIAL
            if len(hits) < 2
            else AnswerStatus.ANSWERED
        )
        return KnowledgeAnswer(
            correlation_id=question.correlation_id,
            status=status,
            answer=answer,
            claims=claims,
            citations=citations,
            active_trade_warning=(
                "An active trade exists; current broker state and risk authority remain "
                "authoritative."
                if question.active_trade
                else None
            ),
        )
