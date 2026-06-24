from __future__ import annotations

import logging
import os

import dramatiq
import dramatiq.middleware
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from dramatiq.brokers.stub import StubBroker

from shared.config import settings

logger = logging.getLogger(__name__)


def init_broker() -> RabbitmqBroker | StubBroker:
    if os.environ.get("UNIT_TESTS") == "1":
        broker: RabbitmqBroker | StubBroker = StubBroker()
        broker.emit_after("process_boot")
    else:
        logger.info("dramatiq broker connecting to %s", settings.rabbitmq_url)
        broker = RabbitmqBroker(url=settings.rabbitmq_url)
    broker.add_middleware(dramatiq.middleware.AsyncIO())
    dramatiq.set_broker(broker)
    return broker
