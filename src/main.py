from __future__ import annotations

import asyncio
from server.main import app
from configs.config import settings

import uvicorn


def main():
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
