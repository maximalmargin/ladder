"""Cost simulation framework for comparing routing strategies."""

from __future__ import annotations

from dataclasses import dataclass, field

from .cost import calculate_cost
from .levels import LEVEL_CONFIGS
from .models import LadderLevel, TokenUsage


@dataclass
class TaskScenario:
    """A hypothetical task with predefined classification and token usage."""

    task: str
    true_level: LadderLevel
    estimated_input_tokens: int
    estimated_output_tokens: int


@dataclass
class SimulationResult:
    """Results from running a simulation."""

    strategy_name: str
    tasks: list[TaskScenario]
    total_cost: float
    per_task_costs: list[float]
    levels_used: dict[LadderLevel, int] = field(default_factory=dict)


class Simulator:
    """Simulate cost of different routing strategies on task scenarios."""

    def run_ladder(self, scenarios: list[TaskScenario]) -> SimulationResult:
        """Simulate ladder routing — each task goes to its true_level."""
        per_task_costs: list[float] = []
        levels_used: dict[LadderLevel, int] = {}

        for scenario in scenarios:
            level = scenario.true_level
            usage = TokenUsage(
                input_tokens=scenario.estimated_input_tokens,
                output_tokens=scenario.estimated_output_tokens,
            )
            # Classification call cost (always uses intern/Haiku pricing)
            classifier_cost = calculate_cost(
                LadderLevel.intern,
                TokenUsage(input_tokens=200, output_tokens=100),
                description="Classification",
            )
            agent_cost = calculate_cost(level, usage, description=f"Agent ({level.value})")
            total = classifier_cost.cost_usd + agent_cost.cost_usd
            per_task_costs.append(total)
            levels_used[level] = levels_used.get(level, 0) + 1

        return SimulationResult(
            strategy_name="Ladder (smart routing)",
            tasks=scenarios,
            total_cost=sum(per_task_costs),
            per_task_costs=per_task_costs,
            levels_used=levels_used,
        )

    def run_fixed_level(
        self, scenarios: list[TaskScenario], level: LadderLevel
    ) -> SimulationResult:
        """Simulate always using a single fixed level for all tasks."""
        per_task_costs: list[float] = []
        levels_used: dict[LadderLevel, int] = {level: len(scenarios)}

        for scenario in scenarios:
            usage = TokenUsage(
                input_tokens=scenario.estimated_input_tokens,
                output_tokens=scenario.estimated_output_tokens,
            )
            cost = calculate_cost(level, usage, description=f"Agent ({level.value})")
            per_task_costs.append(cost.cost_usd)

        return SimulationResult(
            strategy_name=f"Always {level.value.title()}",
            tasks=scenarios,
            total_cost=sum(per_task_costs),
            per_task_costs=per_task_costs,
            levels_used=levels_used,
        )

    def compare(self, results: list[SimulationResult]) -> str:
        """Format a comparison table of simulation results."""
        if not results:
            return "No results to compare."

        lines: list[str] = []
        n_tasks = len(results[0].tasks)

        # Header
        lines.append(f"Cost Comparison ({n_tasks} tasks)")
        lines.append("=" * 70)
        lines.append(
            f"  {'Strategy':<30} {'Total Cost':>12} {'Avg/Task':>12} {'Savings':>10}"
        )
        lines.append("-" * 70)

        # Find most expensive for savings calculation
        max_cost = max(r.total_cost for r in results)

        for result in results:
            avg = result.total_cost / n_tasks if n_tasks > 0 else 0.0
            if max_cost > 0:
                savings = (1.0 - result.total_cost / max_cost) * 100
            else:
                savings = 0.0
            lines.append(
                f"  {result.strategy_name:<30} "
                f"${result.total_cost:>10.4f} "
                f"${avg:>10.6f} "
                f"{savings:>8.1f}%"
            )

        lines.append("-" * 70)

        # Level breakdown for ladder
        for result in results:
            if result.levels_used and len(result.levels_used) > 1:
                lines.append(f"\n  {result.strategy_name} — Level breakdown:")
                for level, count in sorted(
                    result.levels_used.items(), key=lambda x: list(LadderLevel).index(x[0])
                ):
                    pct = count / n_tasks * 100 if n_tasks > 0 else 0
                    lines.append(f"    {level.value:<12} {count:>4} tasks ({pct:>5.1f}%)")

        return "\n".join(lines)


# ── Built-in scenarios ──────────────────────────────────────────────────

def _make_tasks(distribution: dict[LadderLevel, tuple[int, int, int]]) -> list[TaskScenario]:
    """Build task scenarios from a distribution.

    distribution maps LadderLevel -> (count, avg_input_tokens, avg_output_tokens).
    """
    scenarios: list[TaskScenario] = []
    descriptions: dict[LadderLevel, str] = {
        LadderLevel.intern: "Fix typo / formatting",
        LadderLevel.junior: "Write simple function / test",
        LadderLevel.mid: "Implement feature / debug issue",
        LadderLevel.senior: "Multi-file refactor / optimization",
        LadderLevel.staff: "Architecture design / system integration",
        LadderLevel.principal: "Org-wide migration strategy",
    }
    for level, (count, inp, out) in distribution.items():
        for i in range(count):
            scenarios.append(
                TaskScenario(
                    task=f"{descriptions.get(level, 'Task')} #{i+1}",
                    true_level=level,
                    estimated_input_tokens=inp,
                    estimated_output_tokens=out,
                )
            )
    return scenarios


TYPICAL_WORKLOAD = _make_tasks({
    LadderLevel.intern: (25, 300, 150),
    LadderLevel.junior: (25, 500, 300),
    LadderLevel.mid: (15, 1000, 600),
    LadderLevel.senior: (15, 2000, 1000),
    LadderLevel.staff: (10, 3000, 1500),
    LadderLevel.principal: (10, 5000, 3000),
})

DOC_HEAVY_SPRINT = _make_tasks({
    LadderLevel.intern: (50, 300, 200),
    LadderLevel.junior: (30, 500, 300),
    LadderLevel.mid: (15, 1000, 500),
    LadderLevel.senior: (5, 1500, 800),
})

ARCHITECTURE_WEEK = _make_tasks({
    LadderLevel.mid: (20, 1000, 600),
    LadderLevel.senior: (20, 2000, 1200),
    LadderLevel.staff: (40, 3000, 2000),
    LadderLevel.principal: (20, 5000, 3000),
})

BUG_BASH = _make_tasks({
    LadderLevel.intern: (10, 300, 150),
    LadderLevel.junior: (20, 500, 300),
    LadderLevel.mid: (40, 1000, 600),
    LadderLevel.senior: (20, 2000, 1000),
    LadderLevel.staff: (10, 3000, 1500),
})

BUILTIN_SCENARIOS: dict[str, list[TaskScenario]] = {
    "Typical Workload": TYPICAL_WORKLOAD,
    "Documentation-Heavy Sprint": DOC_HEAVY_SPRINT,
    "Architecture Week": ARCHITECTURE_WEEK,
    "Bug Bash": BUG_BASH,
}


def run_all_comparisons() -> str:
    """Run all built-in scenarios and return formatted comparison tables."""
    sim = Simulator()
    sections: list[str] = []

    for name, scenarios in BUILTIN_SCENARIOS.items():
        results = [
            sim.run_fixed_level(scenarios, LadderLevel.principal),  # Most expensive
            sim.run_fixed_level(scenarios, LadderLevel.mid),        # Middle
            sim.run_fixed_level(scenarios, LadderLevel.intern),     # Cheapest
            sim.run_ladder(scenarios),                               # Smart routing
        ]
        sections.append(f"\n{'#' * 70}")
        sections.append(f"  Scenario: {name}")
        sections.append(f"{'#' * 70}\n")
        sections.append(sim.compare(results))

    return "\n".join(sections)
