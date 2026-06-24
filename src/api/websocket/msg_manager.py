from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from core.game.services import GameService
from starlette.websockets import WebSocket, WebSocketState

from shared.message import WSMessage, WSMessageSubtype, WSMessageType

logger = logging.getLogger(__name__)

type MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class WebsocketMsgManager:

    def __init__(self, websocket: WebSocket, game_service: GameService) -> None:
        self._ws = websocket
        self._game_service = game_service
        self._handlers: dict[WSMessageSubtype, MessageHandler] = {}
        self._game_session_id: UUID | None = None
        self._initial_fen: str = ""
        self._ctx_user_id: str = ""
        self._ctx_username: str = ""
        self._ctx_level: int = 1

    def register_handler(self, subtype: WSMessageSubtype, handler: MessageHandler) -> None:
        self._handlers[subtype] = handler

    def register_game_service(
        self,
        game_session_id: UUID,
        initial_fen: str,
        user_id: str = "",
        username: str = "",
        level: int = 1,
    ) -> None:
        self._game_session_id = game_session_id
        self._initial_fen = initial_fen
        self._ctx_user_id = user_id
        self._ctx_username = username
        self._ctx_level = level

        self._handlers[WSMessageSubtype.ERROR] = self._handle_error
        self._handlers[WSMessageSubtype.MOVE] = self._handle_move
        self._handlers[WSMessageSubtype.QUERY] = self._handle_query

    async def send_message(self, msg: WSMessage) -> None:
        if self._ws.client_state == WebSocketState.CONNECTED:
            try:
                await self._ws.send_json(msg.model_dump(mode="json"))
            except Exception:
                pass

    async def send_move(self, move: str, fen: str = "", message: str = "") -> None:
        await self.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.MOVE,
            payload={"move": move, "fen": fen, "message": message},
        ))

    async def send_notification(self, subtype: WSMessageSubtype, payload: Any = None) -> None:
        await self.send_message(WSMessage(
            type=WSMessageType.NOTIFICATION,
            subtype=subtype,
            payload=payload,
        ))

    async def send_score(self, grade: str, delta: int, reason: str) -> None:
        await self.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.MOVE_RESULT,
            payload={"grade": grade, "delta": delta, "reason": reason},
        ))

    async def send_start_game(self, level: int, fen: str, white: str = "student") -> None:
        await self.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.START_GAME,
            payload={"level": level, "fen": fen, "white": white},
        ))

    async def handle_raw_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")
        if msg_type == WSMessageType.PING.value:
            return

        subtype_str = data.get("subtype", "")
        try:
            subtype = WSMessageSubtype(subtype_str)
        except ValueError:
            return

        handler = self._handlers.get(subtype)
        if handler:
            await handler(data)

    async def _handle_error(self, data: dict) -> None:
        await self.send_notification(
            WSMessageSubtype.ERROR,
            data.get("payload", "unknown error"),
        )

    async def _handle_move(self, data: dict) -> None:
        payload = data.get("payload", {})
        move = str(payload.get("move", ""))
        fen = str(payload.get("fen", ""))

        if not move:
            await self.send_notification(WSMessageSubtype.ERROR, "move is required")
            return

        if not self._game_session_id:
            await self.send_notification(WSMessageSubtype.ERROR, "no active game session")
            return

        try:
            result = await self._game_service.handle_move(
                user_id=self._ctx_user_id,
                username=self._ctx_username,
                level=self._ctx_level,
                move=move,
                fen=fen or self._initial_fen,
                game_session_id=str(self._game_session_id),
            )

            if result.move:
                await self.send_move(result.move, result.fen, "")

            await self.send_score(result.score_grade, result.score, result.explanation or "")

            if result.explanation:
                await self.send_message(WSMessage(
                    type=WSMessageType.GAME,
                    subtype=WSMessageSubtype.EXPLAIN,
                    payload={"message": result.explanation},
                ))
        except Exception:
            logger.exception("failed to handle move")
            await self.send_notification(WSMessageSubtype.ERROR, "failed to process move")

    async def _handle_query(self, data: dict) -> None:
        payload = data.get("payload", {})
        query = str(payload.get("query", ""))
        fen = str(payload.get("fen", ""))

        if not query:
            await self.send_notification(WSMessageSubtype.ERROR, "query is required")
            return

        if not self._game_session_id:
            await self.send_notification(WSMessageSubtype.ERROR, "no active game session")
            return

        try:
            result = await self._game_service.handle_query(
                user_id=self._ctx_user_id,
                username=self._ctx_username,
                level=self._ctx_level,
                query=query,
                fen=fen or self._initial_fen,
                game_session_id=str(self._game_session_id),
            )

            if result.explanation:
                await self.send_message(WSMessage(
                    type=WSMessageType.GAME,
                    subtype=WSMessageSubtype.EXPLAIN,
                    payload={"message": result.explanation},
                ))
        except Exception:
            logger.exception("failed to handle query")
            await self.send_notification(WSMessageSubtype.ERROR, "failed to process query")
