"""Main harness: classify -> route -> escalate."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from .agent import LadderAgent
from .classifier import classify_task
from .levels import next_level
from .models import (
    EscalationReason,
    LadderLevel,
    TaskResult,
)

MAX_ESCALATIONS = 3
CONFIDENCE_THRESHOLD = 0.7


class Orchestrator:
    """Routes tasks through the ladder based on classification."""

    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        self.client = client or AsyncAnthropic()

    async def run(self, task: str, context: str = "") -> TaskResult:
        """Classify a task, route to the appropriate agent, and handle escalation."""
        classification, classifier_cost = await classify_task(self.client, task)
        costs = [classifier_cost]
        escalations: list[EscalationReason] = []

        level = classification.level
        initial_level = level

        # Bump level if classifier confidence is low
        if classification.confidence < CONFIDENCE_THRESHOLD:
            bumped = next_level(level)
            if bumped is not None:
                level = bumped
                escalations.append(EscalationReason.low_confidence)

        # Run agent with escalation loop
        escalation_count = 0
        while escalation_count <= MAX_ESCALATIONS:
            agent = LadderAgent(self.client, level)
            response = await agent.run(task, context)
            costs.append(response.cost)

            if not response.escalated:
                total_cost = sum(c.cost_usd for c in costs)
                return TaskResult(
                    task=task,
                    classification=classification,
                    initial_level=initial_level,
                    final_level=level,
                    response=response.text,
                    escalations=escalations,
                    costs=costs,
                    total_cost_usd=total_cost,
                )

            # Agent requested escalation
            escalations.append(EscalationReason.self_escalation)
            escalation_count += 1
            higher = next_level(level)
            if higher is None:
                # Already at principal — use the escalation response as-is
                total_cost = sum(c.cost_usd for c in costs)
                return TaskResult(
                    task=task,
                    classification=classification,
                    initial_level=initial_level,
                    final_level=level,
                    response=response.text,
                    escalations=escalations,
                    costs=costs,
                    total_cost_usd=total_cost,
                )
            level = higher

        # Max escalations reached — return last response
        total_cost = sum(c.cost_usd for c in costs)
        return TaskResult(
            task=task,
            classification=classification,
            initial_level=initial_level,
            final_level=level,
            response=response.text,
            escalations=escalations,
            costs=costs,
            total_cost_usd=total_cost,
        )
