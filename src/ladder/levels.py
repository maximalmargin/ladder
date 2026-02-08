"""Level configurations mapping ladder levels to models, tokens, and pricing."""

from __future__ import annotations

from dataclasses import dataclass

from .models import LadderLevel


@dataclass(frozen=True)
class Pricing:
    """Per-token pricing for a model tier."""

    input_per_mtok: float
    output_per_mtok: float


@dataclass(frozen=True)
class LevelConfig:
    """Configuration for a single ladder level."""

    level: LadderLevel
    model_id: str
    max_output_tokens: int
    pricing: Pricing
    description: str


LEVEL_CONFIGS: dict[LadderLevel, LevelConfig] = {
    LadderLevel.intern: LevelConfig(
        level=LadderLevel.intern,
        model_id="claude-haiku-4-5-20251001",
        max_output_tokens=2048,
        pricing=Pricing(input_per_mtok=1.00, output_per_mtok=5.00),
        description="Simple fixes: typos, formatting, trivial docstrings",
    ),
    LadderLevel.junior: LevelConfig(
        level=LadderLevel.junior,
        model_id="claude-haiku-4-5-20251001",
        max_output_tokens=4096,
        pricing=Pricing(input_per_mtok=1.00, output_per_mtok=5.00),
        description="Straightforward tasks: basic implementations, simple tests",
    ),
    LadderLevel.mid: LevelConfig(
        level=LadderLevel.mid,
        model_id="claude-sonnet-4-5-20250929",
        max_output_tokens=8192,
        pricing=Pricing(input_per_mtok=3.00, output_per_mtok=15.00),
        description="Moderate tasks: feature implementation, debugging, code review",
    ),
    LadderLevel.senior: LevelConfig(
        level=LadderLevel.senior,
        model_id="claude-sonnet-4-5-20250929",
        max_output_tokens=16384,
        pricing=Pricing(input_per_mtok=3.00, output_per_mtok=15.00),
        description="Complex tasks: multi-file changes, performance optimization",
    ),
    LadderLevel.staff: LevelConfig(
        level=LadderLevel.staff,
        model_id="claude-opus-4-6",
        max_output_tokens=32768,
        pricing=Pricing(input_per_mtok=5.00, output_per_mtok=25.00),
        description="System-level tasks: architecture design, cross-team coordination",
    ),
    LadderLevel.principal: LevelConfig(
        level=LadderLevel.principal,
        model_id="claude-opus-4-6",
        max_output_tokens=65536,
        pricing=Pricing(input_per_mtok=5.00, output_per_mtok=25.00),
        description="Strategic tasks: system migrations, org-wide technical vision",
    ),
}

_LEVEL_ORDER = list(LadderLevel)


def get_config(level: LadderLevel) -> LevelConfig:
    """Get the configuration for a given level."""
    return LEVEL_CONFIGS[level]


def next_level(level: LadderLevel) -> LadderLevel | None:
    """Get the next level up in the ladder, or None if already at principal."""
    idx = _LEVEL_ORDER.index(level)
    if idx + 1 < len(_LEVEL_ORDER):
        return _LEVEL_ORDER[idx + 1]
    return None
