"""Pydantic data models and enums for the ladder harness."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LadderLevel(str, Enum):
    """Career ladder levels mapping to LLM capability tiers."""

    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    staff = "staff"
    principal = "principal"


class TaskCategory(str, Enum):
    """Categories of software engineering tasks."""

    code_review = "code_review"
    implementation = "implementation"
    debugging = "debugging"
    testing = "testing"
    architecture = "architecture"
    documentation = "documentation"
    refactoring = "refactoring"


class ClassificationResult(BaseModel):
    """Result from the task complexity classifier."""

    level: LadderLevel
    category: TaskCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    estimated_complexity: int = Field(ge=1, le=10)


class TokenUsage(BaseModel):
    """Token usage from a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0


class CostRecord(BaseModel):
    """Cost record for a single API call."""

    level: LadderLevel
    usage: TokenUsage
    cost_usd: float
    description: str = ""


class EscalationReason(str, Enum):
    """Why a task was escalated to a higher level."""

    low_confidence = "low_confidence"
    self_escalation = "self_escalation"


class AgentResponse(BaseModel):
    """Response from a ladder agent."""

    text: str
    escalated: bool = False
    escalation_reason: EscalationReason | None = None
    cost: CostRecord


class TaskResult(BaseModel):
    """Final result of processing a task through the harness."""

    task: str
    classification: ClassificationResult
    initial_level: LadderLevel
    final_level: LadderLevel
    response: str
    escalations: list[EscalationReason] = Field(default_factory=list)
    costs: list[CostRecord] = Field(default_factory=list)
    total_cost_usd: float = 0.0
