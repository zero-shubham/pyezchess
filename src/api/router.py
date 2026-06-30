from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.docs.docs import router as docs_router
from api.v1.auth import router as auth_router
from api.v1.game_sessions import router as game_sessions_router
from api.v1.users import router as users_router
from api.v1.websocket import router as ws_router
from shared.config import settings
from core.game.session_manager import SessionManager
from core.agent import PromptGetter


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "prompts"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from shared.migrate import run_migrations

    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    PromptGetter(PROMPTS_DIR)
    SessionManager().start_ping_monitor()
    await run_migrations("upgrade", "head")
    logger.info("server started on port %d", settings.port)
    yield
    logger.info("server shutting down")


app = FastAPI(
    title="ezchess",
    description="AI Chess Instructor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(game_sessions_router)
app.include_router(ws_router)
app.include_router(docs_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
