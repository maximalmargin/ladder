"""Tests for ladder.models — enums and Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ladder.models import (
    AgentResponse,
    ClassificationResult,
    CostRecord,
    EscalationReason,
    LadderLevel,
    TaskCategory,
    TaskResult,
    TokenUsage,
)


# ── Enum tests ──────────────────────────────────────────────────────────

class TestLadderLevel:
    def test_all_values(self):
        expected = ["intern", "junior", "mid", "senior", "staff", "principal"]
        assert [l.value for l in LadderLevel] == expected

    def test_string_access(self):
        assert LadderLevel("intern") is LadderLevel.intern
        assert LadderLevel("principal") is LadderLevel.principal

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            LadderLevel("invalid")

    def test_is_str_enum(self):
        assert isinstance(LadderLevel.intern, str)
        assert LadderLevel.intern == "intern"


class TestTaskCategory:
    def test_all_values(self):
        expected = [
            "code_review", "implementation", "debugging", "testing",
            "architecture", "documentation", "refactoring",
        ]
        assert [c.value for c in TaskCategory] == expected

    def test_string_access(self):
        assert TaskCategory("debugging") is TaskCategory.debugging

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            TaskCategory("invalid")


class TestEscalationReason:
    def test_values(self):
        assert EscalationReason.low_confidence.value == "low_confidence"
        assert EscalationReason.self_escalation.value == "self_escalation"

    def test_count(self):
        assert len(EscalationReason) == 2


# ── Pydantic model tests ───────────────────────────────────────────────

class TestClassificationResult:
    def test_valid(self):
        result = ClassificationResult(
            level=LadderLevel.mid,
            category=TaskCategory.implementation,
            confidence=0.85,
            reasoning="Moderate complexity",
            estimated_complexity=5,
        )
        assert result.level == LadderLevel.mid
        assert result.confidence == 0.85

    def test_confidence_lower_bound(self):
        result = ClassificationResult(
            level=LadderLevel.intern,
            category=TaskCategory.documentation,
            confidence=0.0,
            reasoning="test",
            estimated_complexity=1,
        )
        assert result.confidence == 0.0

    def test_confidence_upper_bound(self):
        result = ClassificationResult(
            level=LadderLevel.intern,
            category=TaskCategory.documentation,
            confidence=1.0,
            reasoning="test",
            estimated_complexity=1,
        )
        assert result.confidence == 1.0

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                level=LadderLevel.intern,
                category=TaskCategory.documentation,
                confidence=-0.1,
                reasoning="test",
                estimated_complexity=1,
            )

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                level=LadderLevel.intern,
                category=TaskCategory.documentation,
                confidence=1.1,
                reasoning="test",
                estimated_complexity=1,
            )

    def test_complexity_lower_bound(self):
        result = ClassificationResult(
            level=LadderLevel.intern,
            category=TaskCategory.documentation,
            confidence=0.5,
            reasoning="test",
            estimated_complexity=1,
        )
        assert result.estimated_complexity == 1

    def test_complexity_upper_bound(self):
        result = ClassificationResult(
            level=LadderLevel.intern,
            category=TaskCategory.documentation,
            confidence=0.5,
            reasoning="test",
            estimated_complexity=10,
        )
        assert result.estimated_complexity == 10

    def test_complexity_below_one_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                level=LadderLevel.intern,
                category=TaskCategory.documentation,
                confidence=0.5,
                reasoning="test",
                estimated_complexity=0,
            )

    def test_complexity_above_ten_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationResult(
                level=LadderLevel.intern,
                category=TaskCategory.documentation,
                confidence=0.5,
                reasoning="test",
                estimated_complexity=11,
            )


class TestTokenUsage:
    def test_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_custom_values(self):
        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500

    def test_large_values(self):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
        assert usage.input_tokens == 1_000_000


class TestCostRecord:
    def test_valid(self):
        record = CostRecord(
            level=LadderLevel.senior,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            cost_usd=0.001,
            description="Test",
        )
        assert record.level == LadderLevel.senior
        assert record.cost_usd == 0.001

    def test_default_description(self):
        record = CostRecord(
            level=LadderLevel.intern,
            usage=TokenUsage(),
            cost_usd=0.0,
        )
        assert record.description == ""

    def test_zero_cost(self):
        record = CostRecord(
            level=LadderLevel.intern,
            usage=TokenUsage(),
            cost_usd=0.0,
        )
        assert record.cost_usd == 0.0


class TestAgentResponse:
    def test_basic(self):
        resp = AgentResponse(
            text="Hello",
            cost=CostRecord(
                level=LadderLevel.intern,
                usage=TokenUsage(input_tokens=10, output_tokens=5),
                cost_usd=0.0001,
            ),
        )
        assert resp.text == "Hello"
        assert resp.escalated is False
        assert resp.escalation_reason is None

    def test_escalated(self):
        resp = AgentResponse(
            text="ESCALATE: too complex",
            escalated=True,
            escalation_reason=EscalationReason.self_escalation,
            cost=CostRecord(
                level=LadderLevel.mid,
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                cost_usd=0.001,
            ),
        )
        assert resp.escalated is True
        assert resp.escalation_reason == EscalationReason.self_escalation


class TestTaskResult:
    def test_basic(self):
        result = TaskResult(
            task="Fix typo",
            classification=ClassificationResult(
                level=LadderLevel.intern,
                category=TaskCategory.documentation,
                confidence=0.9,
                reasoning="Simple fix",
                estimated_complexity=1,
            ),
            initial_level=LadderLevel.intern,
            final_level=LadderLevel.intern,
            response="Fixed the typo.",
        )
        assert result.task == "Fix typo"
        assert result.escalations == []
        assert result.costs == []
        assert result.total_cost_usd == 0.0

    def test_with_escalations(self):
        result = TaskResult(
            task="Complex task",
            classification=ClassificationResult(
                level=LadderLevel.mid,
                category=TaskCategory.implementation,
                confidence=0.6,
                reasoning="Might be complex",
                estimated_complexity=6,
            ),
            initial_level=LadderLevel.mid,
            final_level=LadderLevel.senior,
            response="Done",
            escalations=[EscalationReason.low_confidence],
            costs=[
                CostRecord(
                    level=LadderLevel.mid,
                    usage=TokenUsage(input_tokens=100, output_tokens=50),
                    cost_usd=0.001,
                )
            ],
            total_cost_usd=0.001,
        )
        assert len(result.escalations) == 1
        assert result.final_level == LadderLevel.senior
