"""Agent abstraction wrapping Claude API calls per ladder level."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from .cost import calculate_cost
from .levels import get_config
from .models import (
    AgentResponse,
    CostRecord,
    EscalationReason,
    LadderLevel,
    TokenUsage,
)
from .prompts import LEVEL_PROMPTS

ESCALATE_PREFIX = "ESCALATE:"


class LadderAgent:
    """An agent tied to a specific ladder level."""

    def __init__(self, client: AsyncAnthropic, level: LadderLevel) -> None:
        self.client = client
        self.level = level
        self.config = get_config(level)

    async def run(self, task: str, context: str = "") -> AgentResponse:
        """Run the agent on a task, returning text and escalation info."""
        user_content = task
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{task}"

        response = await self.client.messages.create(
            model=self.config.model_id,
            max_tokens=self.config.max_output_tokens,
            system=LEVEL_PROMPTS[self.level],
            messages=[{"role": "user", "content": user_content}],
        )

        text = response.content[0].text
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        cost = calculate_cost(
            self.level, usage, description=f"Agent ({self.level.value})"
        )

        escalated = text.strip().upper().startswith(ESCALATE_PREFIX.upper())

        return AgentResponse(
            text=text,
            escalated=escalated,
            escalation_reason=EscalationReason.self_escalation if escalated else None,
            cost=cost,
        )
