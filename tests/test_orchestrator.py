"""Tests for ladder.orchestrator — full flow with mocked classifier and agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ladder.models import (
    ClassificationResult,
    CostRecord,
    EscalationReason,
    LadderLevel,
    TaskCategory,
    TokenUsage,
)
from ladder.orchestrator import CONFIDENCE_THRESHOLD, MAX_ESCALATIONS, Orchestrator

from .conftest import make_api_response


def _make_classifier_response(
    level: str = "mid",
    category: str = "implementation",
    confidence: float = 0.85,
    reasoning: str = "Test",
    complexity: int = 5,
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Build a mock API response for the classifier."""
    data = {
        "level": level,
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
        "estimated_complexity": complexity,
    }
    return make_api_response(json.dumps(data), input_tokens, output_tokens)


class TestOrchestratorFullFlow:
    @pytest.mark.asyncio
    async def test_simple_flow_no_escalation(self):
        """Simple task: classify → route → respond without escalation."""
        client = AsyncMock()
        # First call: classifier, Second call: agent
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(level="intern", confidence=0.9, complexity=1),
                make_api_response("Fixed the typo.", 80, 30),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Fix typo in README")

        assert result.classification.level == LadderLevel.intern
        assert result.initial_level == LadderLevel.intern
        assert result.final_level == LadderLevel.intern
        assert result.response == "Fixed the typo."
        assert result.escalations == []
        assert len(result.costs) == 2  # classifier + agent

    @pytest.mark.asyncio
    async def test_confidence_bump(self):
        """Low confidence (< 0.7) triggers a bump to the next level."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(
                    level="junior", confidence=0.5, complexity=3
                ),
                make_api_response("Implemented the feature.", 200, 100),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Build user login")

        assert result.classification.level == LadderLevel.junior
        assert result.initial_level == LadderLevel.junior
        # Should have been bumped from junior to mid due to low confidence
        assert result.final_level == LadderLevel.mid
        assert EscalationReason.low_confidence in result.escalations

    @pytest.mark.asyncio
    async def test_confidence_at_threshold_no_bump(self):
        """Confidence exactly at threshold (0.7) does NOT trigger a bump."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(level="junior", confidence=0.7, complexity=3),
                make_api_response("Done.", 100, 50),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Simple task")

        assert result.final_level == LadderLevel.junior
        assert EscalationReason.low_confidence not in result.escalations

    @pytest.mark.asyncio
    async def test_self_escalation_chain(self):
        """Agent escalates → re-run at next level → success."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(level="mid", confidence=0.85, complexity=5),
                # mid agent escalates
                make_api_response("ESCALATE: needs senior help", 200, 30),
                # senior agent succeeds
                make_api_response("Refactored the module.", 300, 150),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Refactor authentication module")

        assert result.initial_level == LadderLevel.mid
        assert result.final_level == LadderLevel.senior
        assert EscalationReason.self_escalation in result.escalations
        assert result.response == "Refactored the module."
        assert len(result.costs) == 3  # classifier + mid agent + senior agent

    @pytest.mark.asyncio
    async def test_double_escalation(self):
        """Agent escalates twice: mid → senior → staff."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(level="mid", confidence=0.9, complexity=5),
                make_api_response("ESCALATE: too complex", 200, 30),
                make_api_response("ESCALATE: needs system thinking", 300, 30),
                make_api_response("Here is the architecture.", 500, 300),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Design microservice architecture")

        assert result.final_level == LadderLevel.staff
        assert result.escalations.count(EscalationReason.self_escalation) == 2
        assert len(result.costs) == 4

    @pytest.mark.asyncio
    async def test_max_escalations_cap(self):
        """After MAX_ESCALATIONS (3), stop escalating and return last response."""
        client = AsyncMock()
        responses = [
            _make_classifier_response(level="intern", confidence=0.9, complexity=1),
        ]
        # Each agent escalates (intern → junior → mid → senior, then 4th escalation hits cap)
        for _ in range(MAX_ESCALATIONS + 1):
            responses.append(make_api_response("ESCALATE: need more", 100, 20))

        client.messages.create = AsyncMock(side_effect=responses)
        orch = Orchestrator(client)
        result = await orch.run("Impossible task")

        assert result.response == "ESCALATE: need more"
        assert len(result.escalations) == MAX_ESCALATIONS + 1  # including final
        # intern + 3 escalations = senior (intern→junior→mid→senior)
        # The 4th escalation attempt happens at senior, which escalates to staff,
        # but the loop exits because escalation_count > MAX_ESCALATIONS
        total_agent_calls = MAX_ESCALATIONS + 1
        assert len(result.costs) == 1 + total_agent_calls  # classifier + agents

    @pytest.mark.asyncio
    async def test_already_at_principal_no_crash(self):
        """If already at principal and agent escalates, return response gracefully."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(
                    level="principal", confidence=0.9, complexity=10
                ),
                make_api_response(
                    "ESCALATE: this is extremely complex", 500, 100
                ),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Redesign the entire platform")

        assert result.final_level == LadderLevel.principal
        assert result.response == "ESCALATE: this is extremely complex"
        # Should not crash — just returns the response as-is

    @pytest.mark.asyncio
    async def test_low_confidence_at_principal_no_bump(self):
        """Low confidence at principal can't bump further — stays at principal."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(
                    level="principal", confidence=0.4, complexity=10
                ),
                make_api_response("Handled at principal.", 500, 200),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Massive migration")

        # next_level(principal) is None, so bump doesn't happen
        assert result.final_level == LadderLevel.principal

    @pytest.mark.asyncio
    async def test_costs_accumulated(self):
        """All costs (classifier + each agent call) are accumulated in result."""
        client = AsyncMock()
        client.messages.create = AsyncMock(
            side_effect=[
                _make_classifier_response(
                    level="mid", confidence=0.9, complexity=5,
                    input_tokens=100, output_tokens=50
                ),
                make_api_response("ESCALATE: need senior", 200, 30),
                make_api_response("Done.", 300, 150),
            ]
        )
        orch = Orchestrator(client)
        result = await orch.run("Implement feature X")

        assert len(result.costs) == 3
        assert result.total_cost_usd == pytest.approx(
            sum(c.cost_usd for c in result.costs)
        )
        assert result.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_default_client_creation(self):
        """Orchestrator creates a default client if none provided."""
        with patch("ladder.orchestrator.AsyncAnthropic") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            orch = Orchestrator()
            assert orch.client is mock_instance


class TestOrchestratorConstants:
    def test_max_escalations_value(self):
        assert MAX_ESCALATIONS == 3

    def test_confidence_threshold_value(self):
        assert CONFIDENCE_THRESHOLD == 0.7
