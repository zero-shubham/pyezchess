from __future__ import annotations

from shared.config import settings

import uvicorn


def main():
    uvicorn.run(
        "api.router:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
