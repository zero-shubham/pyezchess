from __future__ import annotations

import asyncio
import logging

import pytest

from core.tasks.actors import _calculate_credit_usage


def test_async_impl(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        total = asyncio.run(_calculate_credit_usage(1000000, 1000000))

    assert total == pytest.approx(0.42)
    assert "total=$0.42000000" in caplog.text


def test_async_impl_small(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        total = asyncio.run(_calculate_credit_usage(1000, 2000))

    assert total == pytest.approx(0.0007)
    assert "total=$0.00070000" in caplog.text
