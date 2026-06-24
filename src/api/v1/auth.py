from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from configs.config import settings
from domain.user.interface import (
    ErrAdminAlreadyExists,
    ErrInvalidCredentials,
    ErrUserAlreadyExists,
)
from domain.user.service import UserService
from domain.session.model import new_session as create_session_model
from infrastructure.middleware.session import (
    clear_session_cookie,
    generate_session_token,
    hash_token,
    set_session_cookie,
)
from infrastructure.persistence.database import get_uow
from infrastructure.persistence.postgres.session_repository import PostgresSessionRepository
from infrastructure.persistence.postgres.user_repository import PostgresUserRepository
from infrastructure.persistence.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    user_id: UUID
    username: str
    role: str


class UserResponse(BaseModel):
    id: UUID
    username: str
    role: str
    created_at: datetime


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
):
    async with uow:
        user_svc = UserService(PostgresUserRepository(uow.session))
        try:
            user = await user_svc.authenticate(body.email, body.password)
        except ErrInvalidCredentials:
            raise HTTPException(status_code=401, detail="invalid email or password")

        token = generate_session_token()
        token_hash_val = hash_token(token)
        session = create_session_model(
            user_id=user.id,
            token_hash=token_hash_val,
            ip="",
            ua=request.headers.get("user-agent", ""),
            ttl_seconds=settings.session_max_age_seconds,
        )

        session_repo = PostgresSessionRepository(uow.session)
        await session_repo.create(session)

        await uow.commit()

    set_session_cookie(response, token)
    return LoginResponse(user_id=user.id, username=user.username, role=user.role.value)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
):
    async with uow:
        if session_token:
            token_hash_val = hash_token(session_token)
            session_repo = PostgresSessionRepository(uow.session)
            sessions = await session_repo.get_by_user_id(UUID("00000000-0000-0000-0000-000000000000"))
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(
    request: Request,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
):
    if not session_token:
        raise HTTPException(status_code=401, detail="unauthorized")

    async with uow:
        token_hash_val = hash_token(session_token)
        session_repo = PostgresSessionRepository(uow.session)
        session = await session_repo.get_by_token_hash(token_hash_val)
        if not session or session.is_expired():
            raise HTTPException(status_code=401, detail="session invalid or expired")
        user_repo = PostgresUserRepository(uow.session)
        user = await user_repo.find_by_id(session.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="user not found")

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        created_at=user.created_at,
    )
