from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, WebSocket, WebSocketDisconnect

from configs.config import settings
from domain.game.model import GameSessionStatus
from domain.game.service import GameService
from domain.game.session_manager import SessionEntry
from domain.instructor.service import LangGraphInstructor
from domain.instructor.prompt import PromptGetter
from infrastructure.ai.factory import create_llm_client
from infrastructure.ai.provider import LLMProvider, ProviderType
from infrastructure.middleware.session import hash_token
from infrastructure.persistence.database import async_session_factory
from infrastructure.persistence.postgres.session_repository import PostgresSessionRepository
from infrastructure.persistence.postgres.user_repository import PostgresUserRepository
from infrastructure.persistence.unit_of_work import UnitOfWork
from infrastructure.websocket import WebsocketMsgManager
from protocol.message import SessionContext, WSMessageSubtype

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/api/v1/ws/game")
async def game_websocket(
    websocket: WebSocket,
    session_token: str | None = Cookie(
        default=None, alias=settings.session_cookie_name),
    level: int = 1
):
    prompt_getter = PromptGetter()

    await websocket.accept()

    user_id: UUID | None = None
    username = "anonymous"

    if session_token:
        token_hash = hash_token(session_token)
        async with UnitOfWork(async_session_factory) as uow:
            auth_session_repo = PostgresSessionRepository(uow.session)
            user_session = await auth_session_repo.get_by_token_hash(token_hash)
            if user_session and not user_session.is_expired() and user_session.user_id:
                user_repo = PostgresUserRepository(uow.session)
                user = await user_repo.find_by_id(user_session.user_id)
                if user:
                    user_id = user.id
                    username = user.username
                    await auth_session_repo.update_last_active(user_session.id)
                    await uow.commit()

    ws_session_id = uuid4()

    if user_id is None:
        await websocket.close()
        return

    game_service = GameService(async_session_factory)
    msg_manager = WebsocketMsgManager(websocket, game_service)
    game_service.set_msg_manager(msg_manager)

    llm = create_llm_client(LLMProvider(
        type=ProviderType.DEEPSEEK, api_key=settings.deepseek_api_key, model=settings.deepseek_model))

    instructor = LangGraphInstructor(
        llm=llm,
        system_prompt=prompt_getter.main_prompt(),
        user_id=str(user_id),
    )
    game_service.set_instructor(instructor)

    result = await game_service.begin(str(user_id), username, level)

    game_session_id = UUID(
        result.game_session_id) if result.game_session_id else None
    initial_fen = result.fen

    if not game_session_id:
        await msg_manager.send_notification(
            WSMessageSubtype.ERROR,
            "Failed to start game session.",
        )
        await websocket.close()
        return

    entry = SessionEntry(
        session_id=ws_session_id,
        user_id=user_id,
        ws=websocket,
        level=level,
        initial_fen=initial_fen,
        current_fen=initial_fen,
    )

    await game_service.register_session(entry)

    msg_manager.register_game_service(
        game_session_id, initial_fen,
        user_id=str(user_id), username=username, level=level)

    try:
        async for raw in websocket.iter_text():
            await game_service.update_ping(ws_session_id)
            await msg_manager.handle_raw_message(raw)
    except WebSocketDisconnect:
        pass
    finally:
        await game_service.remove_session(ws_session_id)
        try:
            if user_id:
                game_svc = GameService(async_session_factory)
                session = await game_svc.get_session(game_session_id)
                if session:
                    session.status = GameSessionStatus.ABANDONED
                    await game_svc.update_session(session)
                await game_svc.increment_token_usage(game_session_id, 0)
        except Exception:
            pass
