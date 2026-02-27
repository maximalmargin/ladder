"""Shared fixtures for ladder test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ladder.models import (
    ClassificationResult,
    CostRecord,
    LadderLevel,
    TaskCategory,
    TokenUsage,
)


@pytest.fixture
def mock_client():
    """Create a mock AsyncAnthropic client with configurable responses."""
    client = AsyncMock()
    return client


def make_api_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Helper to build a mock Anthropic API response."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    response.content = [content_block]
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


@pytest.fixture
def simple_classification():
    """A simple intern-level classification result."""
    return ClassificationResult(
        level=LadderLevel.intern,
        category=TaskCategory.documentation,
        confidence=0.95,
        reasoning="Simple typo fix",
        estimated_complexity=1,
    )


@pytest.fixture
def complex_classification():
    """A complex staff-level classification result."""
    return ClassificationResult(
        level=LadderLevel.staff,
        category=TaskCategory.architecture,
        confidence=0.85,
        reasoning="System architecture redesign",
        estimated_complexity=9,
    )


@pytest.fixture
def low_confidence_classification():
    """A classification with low confidence (below threshold)."""
    return ClassificationResult(
        level=LadderLevel.mid,
        category=TaskCategory.implementation,
        confidence=0.5,
        reasoning="Unclear task complexity",
        estimated_complexity=5,
    )


@pytest.fixture
def sample_token_usage():
    """Sample token usage fixture."""
    return TokenUsage(input_tokens=500, output_tokens=200)


@pytest.fixture
def sample_cost_record():
    """Sample cost record fixture."""
    return CostRecord(
        level=LadderLevel.mid,
        usage=TokenUsage(input_tokens=500, output_tokens=200),
        cost_usd=0.0045,
        description="Test call",
    )
