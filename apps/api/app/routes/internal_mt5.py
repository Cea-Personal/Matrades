from __future__ import annotations

import base64
import binascii
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db
from modules.connections.mt5_authority import verify_ui_managed_mt5_signature
from packages.shared.config import get_settings

router = APIRouter(prefix="/internal/mt5", tags=["Internal MT5"])


class MT5SignatureInput(BaseModel):
    body_base64: str
    timestamp: str
    nonce: str = Field(min_length=1, max_length=200)
    signature: str = Field(min_length=64, max_length=128)


@router.post("/authenticate")
async def authenticate_mt5_request(
    payload: MT5SignatureInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_matrades_service_token: Annotated[str, Header()],
):
    configured = get_settings().mt5_authority_token.get_secret_value()
    if not configured or not hmac.compare_digest(x_matrades_service_token, configured):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bridge service identity")
    try:
        body = base64.b64decode(payload.body_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid request body encoding"
        ) from exc
    credential_id = await verify_ui_managed_mt5_signature(
        db,
        body=body,
        timestamp=payload.timestamp,
        nonce=payload.nonce,
        signature=payload.signature,
    )
    if credential_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MT5 credential signature")
    return {"authenticated": True, "credential_id": str(credential_id)}
