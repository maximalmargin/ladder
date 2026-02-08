"""Haiku-based task complexity classifier."""

from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from .cost import calculate_cost
from .models import (
    ClassificationResult,
    CostRecord,
    LadderLevel,
    TaskCategory,
    TokenUsage,
)
from .prompts import CLASSIFIER_PROMPT

CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"


async def classify_task(
    client: AsyncAnthropic, task: str
) -> tuple[ClassificationResult, CostRecord]:
    """Classify a task's complexity using Haiku with structured output.

    Returns the classification result and its associated cost record.
    """
    response = await client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=1024,
        system=CLASSIFIER_PROMPT,
        messages=[{"role": "user", "content": task}],
        headers={"anthropic-beta": "output-128k-2025-02-19"},
    )

    text = response.content[0].text
    # Parse the JSON from the response, handling possible markdown fencing
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove markdown code fences
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    data = json.loads(cleaned)

    classification = ClassificationResult(
        level=LadderLevel(data["level"]),
        category=TaskCategory(data["category"]),
        confidence=float(data["confidence"]),
        reasoning=data["reasoning"],
        estimated_complexity=int(data["estimated_complexity"]),
    )

    usage = TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    cost = calculate_cost(LadderLevel.intern, usage, description="Classification")

    return classification, cost
