from __future__ import annotations

import os

os.environ["UNIT_TESTS"] = "1"

import dramatiq
from dramatiq.brokers.stub import StubBroker

# Set StubBroker before any actor modules are imported
_broker = StubBroker()
_broker.emit_after("process_boot")
dramatiq.set_broker(_broker)
