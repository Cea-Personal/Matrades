from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.journal.analytics import aggregate, analytics_rows
from traderx.journal.hypotheses import propose
from traderx.journal.model import (
    JournalAnnotation,
    JournalAttachment,
    JournalEntry,
    ResearchProposal,
)
from traderx.journal.projector import project_completed_activity
from traderx.journal.service import checksum
from traderx.shared.types import InvalidTransition, utc_now
from traderx.strategies.model import StrategyVersion
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/journal", tags=["Journal"], dependencies=[Depends(authenticated_operation_context)]
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class AnnotationCommand(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ProposalCommand(BaseModel):
    hypothesis: str = Field(min_length=8, max_length=10000)
    evidence_entry_ids: list[UUID] = Field(min_length=1)
    strategy_version_id: UUID | None = None


ALLOWED_ATTACHMENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


@router.post("/project", status_code=202)
def project(_: Operator, database: DatabaseSession) -> dict[str, object]:
    created = project_completed_activity(database)
    database.commit()
    return {"created": len(created), "append_only": True}


@router.get("/entries")
def entries(
    _: Viewer,
    database: DatabaseSession,
    source_type: str | None = None,
    instrument_id: UUID | None = None,
) -> dict[str, object]:
    query = select(JournalEntry).order_by(JournalEntry.closed_at.desc())
    if source_type:
        query = query.where(JournalEntry.source_type == source_type)
    if instrument_id:
        query = query.where(JournalEntry.instrument_id == instrument_id)
    return {
        "items": [
            _entry_payload(database, item, include_annotations=True)
            for item in database.scalars(query)
        ]
    }


@router.get("/entries/{entry_id}")
def entry_detail(entry_id: UUID, _: Viewer, database: DatabaseSession) -> dict[str, object]:
    entry = database.get(JournalEntry, entry_id)
    if entry is None:
        raise InvalidTransition("the requested journal entry does not exist")
    return _entry_payload(database, entry, include_annotations=True)


@router.post("/entries/{entry_id}/annotations", status_code=201)
def annotate(
    entry_id: UUID,
    payload: AnnotationCommand,
    context: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    if database.get(JournalEntry, entry_id) is None:
        raise InvalidTransition("the requested journal entry does not exist")
    previous = database.scalar(
        select(JournalAnnotation)
        .where(JournalAnnotation.entry_id == entry_id)
        .order_by(JournalAnnotation.created_at.desc())
        .limit(1)
    )
    annotation = JournalAnnotation(
        entry_id=entry_id,
        supersedes_id=previous.id if previous else None,
        content=payload.content.strip(),
        created_by=context.user.id,
        created_at=utc_now(),
    )
    database.add(annotation)
    database.commit()
    database.refresh(annotation)
    return {
        "id": str(annotation.id),
        "entry_id": str(entry_id),
        "content": annotation.content,
        "supersedes_id": str(annotation.supersedes_id) if annotation.supersedes_id else None,
        "created_at": annotation.created_at.isoformat(),
        "idempotency_key": idempotency_key,
        "append_only": True,
    }


@router.post("/entries/{entry_id}/attachments", status_code=201)
async def attach_screenshot(
    entry_id: UUID,
    context: Operator,
    database: DatabaseSession,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    if database.get(JournalEntry, entry_id) is None:
        raise InvalidTransition("the requested journal entry does not exist")
    media_type = file.content_type or "application/octet-stream"
    if media_type not in ALLOWED_ATTACHMENT_TYPES:
        raise InvalidTransition("journal attachments must be PNG, JPEG, or WebP images")
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise InvalidTransition("journal attachments must be between 1 byte and 5 MB")
    digest = checksum(content)
    attachment = JournalAttachment(
        entry_id=entry_id,
        artifact_ref=f"journal-attachment:{digest}",
        checksum=digest,
        classification="PROTECTED_JOURNAL_EVIDENCE",
        original_name=(file.filename or "screenshot")[:512],
        media_type=media_type,
        content=content,
        uploaded_by=context.user.id,
        uploaded_at=utc_now(),
    )
    database.add(attachment)
    database.commit()
    database.refresh(attachment)
    return {
        "id": str(attachment.id),
        "entry_id": str(entry_id),
        "original_name": attachment.original_name,
        "media_type": attachment.media_type,
        "checksum": attachment.checksum,
        "download_path": f"/api/v1/journal/attachments/{attachment.id}",
        "protected": True,
    }


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: UUID, _: Viewer, database: DatabaseSession) -> Response:
    attachment = database.get(JournalAttachment, attachment_id)
    if attachment is None:
        raise InvalidTransition("the requested journal attachment does not exist")
    return Response(
        content=attachment.content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(attachment.original_name, safe="")
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/analytics")
def analytics(
    _: Viewer,
    database: DatabaseSession,
    dimension: Literal[
        "instrument",
        "asset_class",
        "source_type",
        "strategy_version",
        "time",
        "direction",
        "risk",
        "regime",
        "entry_quality",
        "behavior",
    ] = "instrument",
) -> dict[str, object]:
    rows = analytics_rows(database)
    groups = aggregate(rows, dimension)
    return {
        "dimension": dimension,
        "groups": {
            name: {key: str(value) if key != "count" else value for key, value in values.items()}
            for name, values in groups.items()
        },
        "entry_count": len(rows),
    }


@router.post("/proposals", status_code=201)
def proposal(
    payload: ProposalCommand,
    _: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    entries = [database.get(JournalEntry, entry_id) for entry_id in payload.evidence_entry_ids]
    if any(entry is None for entry in entries):
        raise InvalidTransition("every research proposal evidence link must exist")
    if (
        payload.strategy_version_id
        and database.get(StrategyVersion, payload.strategy_version_id) is None
    ):
        raise InvalidTransition("the linked immutable strategy version does not exist")
    hypothesis = propose(
        text=payload.hypothesis,
        evidence_links=[f"journal:{entry_id}" for entry_id in payload.evidence_entry_ids],
        strategy_version_id=(
            str(payload.strategy_version_id) if payload.strategy_version_id else None
        ),
    )
    record = ResearchProposal(
        strategy_version_id=payload.strategy_version_id,
        evidence_links=list(hypothesis.evidence_links),
        hypothesis=hypothesis.text,
        state=hypothesis.state,
        created_at=utc_now(),
    )
    database.add(record)
    database.commit()
    database.refresh(record)
    return {
        "id": str(record.id),
        "hypothesis": record.hypothesis,
        "evidence_links": record.evidence_links,
        "strategy_version_id": (
            str(record.strategy_version_id) if record.strategy_version_id else None
        ),
        "state": record.state,
        "idempotency_key": idempotency_key,
        "source_strategy_mutated": False,
    }


def _entry_payload(
    database: Session, entry: JournalEntry, *, include_annotations: bool = False
) -> dict[str, object]:
    from traderx.market_data.model import Instrument

    instrument = database.get(Instrument, entry.instrument_id) if entry.instrument_id else None
    payload: dict[str, object] = {
        "id": str(entry.id),
        "source_type": entry.source_type,
        "instrument_id": str(entry.instrument_id) if entry.instrument_id else None,
        "symbol": instrument.symbol if instrument else "UNKNOWN",
        "gross_pnl": str(entry.gross_pnl),
        "net_pnl": str(entry.net_pnl),
        "r_multiple": str(entry.r_multiple) if entry.r_multiple is not None else None,
        "evidence": entry.evidence,
        "closed_at": entry.closed_at.isoformat(),
        "immutable": True,
    }
    if include_annotations:
        payload["annotations"] = [
            {
                "id": str(item.id),
                "content": item.content,
                "supersedes_id": str(item.supersedes_id) if item.supersedes_id else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in database.scalars(
                select(JournalAnnotation)
                .where(JournalAnnotation.entry_id == entry.id)
                .order_by(JournalAnnotation.created_at)
            )
        ]
        payload["attachments"] = [
            {
                "id": str(item.id),
                "original_name": item.original_name,
                "media_type": item.media_type,
                "checksum": item.checksum,
                "download_path": f"/api/v1/journal/attachments/{item.id}",
            }
            for item in database.scalars(
                select(JournalAttachment)
                .where(JournalAttachment.entry_id == entry.id)
                .order_by(JournalAttachment.uploaded_at)
            )
        ]
    return payload
