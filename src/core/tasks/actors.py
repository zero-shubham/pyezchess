from __future__ import annotations

import logging

import dramatiq

from shared.broker import init_broker

logger = logging.getLogger(__name__)

INPUT_COST_PER_TOKEN = 0.14 / 1_000_000
OUTPUT_COST_PER_TOKEN = 0.28 / 1_000_000

init_broker()


async def _calculate_credit_usage(input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens * INPUT_COST_PER_TOKEN) + (output_tokens * OUTPUT_COST_PER_TOKEN)
    logger.info(
        "credit usage: input=%d tokens ($%.8f), output=%d tokens ($%.8f), total=$%.8f",
        input_tokens,
        input_tokens * INPUT_COST_PER_TOKEN,
        output_tokens,
        output_tokens * OUTPUT_COST_PER_TOKEN,
        cost,
    )
    return cost


@dramatiq.actor
async def calculate_credit_usage(input_tokens: int, output_tokens: int) -> float:
    return await _calculate_credit_usage(input_tokens, output_tokens)
