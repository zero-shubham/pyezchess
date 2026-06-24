from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.user.interfaces import (
    ErrAdminAlreadyExists,
    ErrUserAlreadyExists,
)
from core.user.services import UserService
from shared.database import get_uow
from core.user.repository import PostgresUserRepository
from shared.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class CreateUserRequest(BaseModel):
    email: str
    password: str
    username: str


class UserResponse(BaseModel):
    id: UUID
    username: str
    email_hash: str
    role: str
    created_at: datetime


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(body: CreateUserRequest, uow: Annotated[UnitOfWork, Depends(get_uow)]):
    async with uow:
        user_repo = PostgresUserRepository(uow.session)
        user_svc = UserService(user_repo)
        try:
            user = await user_svc.create_user(body.username, body.email, body.password)
        except ErrUserAlreadyExists as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        await uow.commit()

    return UserResponse(
        id=user.id,
        username=user.username,
        email_hash=user.email_hash,
        role=user.role.value,
        created_at=user.created_at,
    )
