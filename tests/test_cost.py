"""OpenAI usage and cost calculation tests."""

from __future__ import annotations

from app.pipeline.cost import empty_usage, usage_from_tokens


def test_empty_usage_is_zero() -> None:
    """Skipped vision reports zero tokens and cost."""
    usage = empty_usage(vision_called=False)
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cost_usd == 0.0
    assert usage.cost_inr == 0.0
    assert usage.vision_called is False
    assert usage.fx_usd_to_inr == 96.78


def test_cost_usd_and_inr_from_tokens() -> None:
    """Cost uses per-1M rates and FX 96.78."""
    # 1M input @ $2.50 + 0.5M output @ $10.00 = $2.50 + $5.00 = $7.50
    usage = usage_from_tokens(
        1_000_000,
        500_000,
        input_usd_per_1m=2.50,
        output_usd_per_1m=10.00,
        fx_usd_to_inr=96.78,
        vision_called=True,
    )
    assert usage.total_tokens == 1_500_000
    assert usage.cost_usd == 7.5
    assert usage.cost_inr == round(7.5 * 96.78, 4)
    assert usage.vision_called is True
