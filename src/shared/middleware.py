from __future__ import annotations

import hashlib
import secrets

from fastapi import Cookie, HTTPException, Request
from fastapi.responses import Response

from shared.config import settings
from core.session.schemas import Session as SessionModel


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def set_session_cookie(response: Response, token: str, max_age: int | None = None):
    if max_age is None:
        max_age = settings.session_max_age_seconds
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        path="/",
    )


class SessionDep:
    def __init__(self, session_repo):
        self._session_repo = session_repo

    def middleware(self, required: bool = False):
        repo = self._session_repo

        async def _mw(
            request: Request,
            session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
        ) -> SessionModel | None:
            if not session_token:
                if required:
                    raise HTTPException(status_code=401, detail="unauthorized")
                return None
            token_hash = hash_token(session_token)
            session = await repo.get_by_token_hash(token_hash)
            if session is None or session.is_expired():
                if required:
                    raise HTTPException(status_code=401, detail="session invalid or expired")
                return None
            return session

        return _mw
