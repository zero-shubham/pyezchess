from __future__ import annotations

import logging
import signal
import threading

from dbos import DBOS, DBOSConfig

from shared.config import settings
from shared.queues import CREDIT_USAGE_QUEUE

from core.tasks.token_usage import calculate_credit_usage  # noqa: F401

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config: DBOSConfig = {
    "name": "ezchess-worker",
    "system_database_url": settings.dbos_system_database_url,
}
DBOS(config=config)
DBOS.launch()

DBOS.register_queue(CREDIT_USAGE_QUEUE)

shutdown_event = threading.Event()


def _shutdown(signum: int, frame: object) -> None:
    logger.info("received signal %d, shutting down", signum)
    shutdown_event.set()


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)

shutdown_event.wait()

logger.info("destroying DBOS")
DBOS.destroy(workflow_completion_timeout_sec=60)
