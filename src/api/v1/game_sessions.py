from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from pydantic import BaseModel

from configs.config import settings
from infrastructure.middleware.session import hash_token
from infrastructure.persistence.database import get_uow
from infrastructure.persistence.postgres.game_repository import PostgresGameRepository
from infrastructure.persistence.postgres.session_repository import PostgresSessionRepository
from infrastructure.persistence.postgres.user_repository import PostgresUserRepository
from infrastructure.persistence.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/game-sessions", tags=["game-sessions"])


class CapturedPieces(BaseModel):
    white: list[str]
    black: list[str]


class GameMetadataResponse(BaseModel):
    white: str
    captured: CapturedPieces


class TokenUsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int


class GameSessionResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    level: int
    status: str
    initial_fen: str
    current_fen: str
    metadata: GameMetadataResponse | None
    token_usage: TokenUsageResponse
    created_at: datetime
    updated_at: datetime


@router.get("/{session_id}", response_model=GameSessionResponse)
async def get_game_session(
    session_id: UUID,
    request: Request,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    session_token: str | None = Cookie(
        default=None, alias=settings.session_cookie_name),
):
    if not session_token:
        raise HTTPException(status_code=401, detail="unauthorized")

    async with uow:
        token_hash_val = hash_token(session_token)
        session_repo = PostgresSessionRepository(uow.session)
        session = await session_repo.get_by_token_hash(token_hash_val)
        if not session or session.is_expired() or not session.user_id:
            raise HTTPException(
                status_code=401, detail="session invalid or expired")

        user_repo = PostgresUserRepository(uow.session)
        user = await user_repo.find_by_id(session.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="user not found")

        game_repo = PostgresGameRepository(uow.session)
        game_session = await game_repo.get_session(session_id)
        if not game_session:
            raise HTTPException(
                status_code=404, detail="game session not found")

        if game_session.user_id != user.id:
            raise HTTPException(status_code=403, detail="forbidden")

    metadata = None
    if game_session.metadata:
        metadata = GameMetadataResponse(
            white=game_session.metadata.white,
            captured=CapturedPieces(
                white=game_session.metadata.captured.get("white", []),
                black=game_session.metadata.captured.get("black", []),
            ),
        )

    return GameSessionResponse(
        id=game_session.id,
        user_id=game_session.user_id,
        level=game_session.level.value,
        status=game_session.status.value,
        initial_fen=game_session.initial_fen,
        current_fen=game_session.current_fen,
        metadata=metadata,
        token_usage=TokenUsageResponse(
            input_tokens=game_session.token_usage.get("input_tokens", 0),
            output_tokens=game_session.token_usage.get("output_tokens", 0),
        ),
        created_at=game_session.created_at,
        updated_at=game_session.updated_at,
    )
