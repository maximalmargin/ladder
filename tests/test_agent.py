"""Tests for ladder.agent — LadderAgent with mocked API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ladder.agent import ESCALATE_PREFIX, LadderAgent
from ladder.models import EscalationReason, LadderLevel

from .conftest import make_api_response


@pytest.fixture
def mock_client():
    return AsyncMock()


class TestLadderAgent:
    @pytest.mark.asyncio
    async def test_basic_response(self, mock_client):
        """Agent returns a normal (non-escalated) response."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Here is the fix.", 150, 80)
        )
        agent = LadderAgent(mock_client, LadderLevel.mid)
        resp = await agent.run("Fix the typo in main.py")

        assert resp.text == "Here is the fix."
        assert resp.escalated is False
        assert resp.escalation_reason is None
        assert resp.cost.level == LadderLevel.mid
        assert resp.cost.usage.input_tokens == 150
        assert resp.cost.usage.output_tokens == 80

    @pytest.mark.asyncio
    async def test_escalation_detected(self, mock_client):
        """Agent recognizes ESCALATE: prefix and flags escalation."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response(
                "ESCALATE: This requires system-level architecture knowledge.", 200, 30
            )
        )
        agent = LadderAgent(mock_client, LadderLevel.junior)
        resp = await agent.run("Redesign the auth system")

        assert resp.escalated is True
        assert resp.escalation_reason == EscalationReason.self_escalation

    @pytest.mark.asyncio
    async def test_escalation_case_insensitive(self, mock_client):
        """ESCALATE detection is case-insensitive."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("escalate: too complex", 100, 20)
        )
        agent = LadderAgent(mock_client, LadderLevel.intern)
        resp = await agent.run("Refactor the entire codebase")

        assert resp.escalated is True

    @pytest.mark.asyncio
    async def test_escalation_with_leading_whitespace(self, mock_client):
        """ESCALATE detection handles leading whitespace."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("  ESCALATE: needs senior help", 100, 20)
        )
        agent = LadderAgent(mock_client, LadderLevel.intern)
        resp = await agent.run("Complex debugging task")

        assert resp.escalated is True

    @pytest.mark.asyncio
    async def test_non_escalation_with_escalate_in_body(self, mock_client):
        """ESCALATE in the middle of text doesn't trigger escalation."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response(
                "You should not ESCALATE: this is fine.", 100, 50
            )
        )
        agent = LadderAgent(mock_client, LadderLevel.mid)
        resp = await agent.run("Simple task")

        assert resp.escalated is False

    @pytest.mark.asyncio
    async def test_correct_model_used_per_level(self, mock_client):
        """Each level uses its configured model ID."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Done", 100, 50)
        )

        level_models = {
            LadderLevel.intern: "claude-haiku-4-5-20251001",
            LadderLevel.junior: "claude-haiku-4-5-20251001",
            LadderLevel.mid: "claude-sonnet-4-5-20250929",
            LadderLevel.senior: "claude-sonnet-4-5-20250929",
            LadderLevel.staff: "claude-opus-4-6",
            LadderLevel.principal: "claude-opus-4-6",
        }

        for level, expected_model in level_models.items():
            mock_client.messages.create.reset_mock()
            agent = LadderAgent(mock_client, level)
            await agent.run("Test task")

            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == expected_model, (
                f"Level {level.value} should use {expected_model}"
            )

    @pytest.mark.asyncio
    async def test_correct_max_tokens_per_level(self, mock_client):
        """Each level uses its configured max_output_tokens."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Done", 100, 50)
        )
        from ladder.levels import LEVEL_CONFIGS

        for level in LadderLevel:
            mock_client.messages.create.reset_mock()
            agent = LadderAgent(mock_client, level)
            await agent.run("Test task")

            call_kwargs = mock_client.messages.create.call_args[1]
            expected_tokens = LEVEL_CONFIGS[level].max_output_tokens
            assert call_kwargs["max_tokens"] == expected_tokens

    @pytest.mark.asyncio
    async def test_context_prepended(self, mock_client):
        """When context is provided, it's prepended to the task."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Done", 100, 50)
        )
        agent = LadderAgent(mock_client, LadderLevel.mid)
        await agent.run("Fix the bug", context="File: main.py\nLine: 42")

        call_kwargs = mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert "Context:" in content
        assert "File: main.py" in content
        assert "Task:" in content
        assert "Fix the bug" in content

    @pytest.mark.asyncio
    async def test_no_context_sends_task_directly(self, mock_client):
        """Without context, the task is sent directly."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Done", 100, 50)
        )
        agent = LadderAgent(mock_client, LadderLevel.mid)
        await agent.run("Fix the bug")

        call_kwargs = mock_client.messages.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        assert content == "Fix the bug"

    @pytest.mark.asyncio
    async def test_cost_calculation(self, mock_client):
        """Cost is calculated correctly for the agent's level."""
        mock_client.messages.create = AsyncMock(
            return_value=make_api_response("Done", 1000, 500)
        )
        agent = LadderAgent(mock_client, LadderLevel.staff)
        resp = await agent.run("Design a system")

        # Staff: $5.00/MTok input, $25.00/MTok output
        # (1000 / 1M) * 5.00 + (500 / 1M) * 25.00 = 0.005 + 0.0125 = 0.0175
        assert resp.cost.cost_usd == pytest.approx(0.0175)
        assert resp.cost.description == "Agent (staff)"
