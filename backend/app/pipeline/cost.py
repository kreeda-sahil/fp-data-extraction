"""OpenAI token usage and USD/INR cost helpers."""

from __future__ import annotations

from app.config import (
    FX_USD_TO_INR,
    OPENAI_INPUT_USD_PER_1M,
    OPENAI_MODEL,
    OPENAI_OUTPUT_USD_PER_1M,
)
from app.schemas import UsageInfo


def empty_usage(vision_called: bool = False) -> UsageInfo:
    """Return a zero-cost usage block."""
    return UsageInfo(
        model=OPENAI_MODEL,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        cost_inr=0.0,
        fx_usd_to_inr=FX_USD_TO_INR,
        vision_called=vision_called,
    )


def usage_from_tokens(
    input_tokens: int,
    output_tokens: int,
    *,
    vision_called: bool = True,
    model: str | None = None,
    input_usd_per_1m: float | None = None,
    output_usd_per_1m: float | None = None,
    fx_usd_to_inr: float | None = None,
) -> UsageInfo:
    """Build UsageInfo from token counts and configured rates."""
    in_rate = OPENAI_INPUT_USD_PER_1M if input_usd_per_1m is None else input_usd_per_1m
    out_rate = OPENAI_OUTPUT_USD_PER_1M if output_usd_per_1m is None else output_usd_per_1m
    fx = FX_USD_TO_INR if fx_usd_to_inr is None else fx_usd_to_inr
    cost_usd = (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate
    return UsageInfo(
        model=model or OPENAI_MODEL,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        total_tokens=int(input_tokens) + int(output_tokens),
        cost_usd=round(cost_usd, 6),
        cost_inr=round(cost_usd * fx, 4),
        fx_usd_to_inr=fx,
        vision_called=vision_called,
    )


def usage_from_openai_response(response, *, vision_called: bool = True) -> UsageInfo:
    """Extract token counts from an OpenAI chat completion response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return empty_usage(vision_called=vision_called)
    input_tokens = getattr(usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "output_tokens", 0) or 0
    return usage_from_tokens(
        int(input_tokens),
        int(output_tokens),
        vision_called=vision_called,
    )
