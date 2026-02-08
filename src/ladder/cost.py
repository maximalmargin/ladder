"""Token-to-USD cost calculation and formatting."""

from __future__ import annotations

from .levels import get_config
from .models import CostRecord, LadderLevel, TokenUsage


def calculate_cost(
    level: LadderLevel, usage: TokenUsage, description: str = ""
) -> CostRecord:
    """Calculate the USD cost for token usage at a given level."""
    config = get_config(level)
    pricing = config.pricing
    input_cost = (usage.input_tokens / 1_000_000) * pricing.input_per_mtok
    output_cost = (usage.output_tokens / 1_000_000) * pricing.output_per_mtok
    return CostRecord(
        level=level,
        usage=usage,
        cost_usd=input_cost + output_cost,
        description=description,
    )


def format_cost_summary(records: list[CostRecord]) -> str:
    """Format a list of cost records into a human-readable summary."""
    if not records:
        return "No API calls made."

    lines = ["Cost Breakdown:", "-" * 50]
    total = 0.0
    for i, rec in enumerate(records, 1):
        desc = rec.description or f"Call {i}"
        lines.append(
            f"  {desc}: ${rec.cost_usd:.6f} "
            f"({rec.level.value}, "
            f"{rec.usage.input_tokens}in/{rec.usage.output_tokens}out)"
        )
        total += rec.cost_usd
    lines.append("-" * 50)
    lines.append(f"  Total: ${total:.6f}")
    return "\n".join(lines)
