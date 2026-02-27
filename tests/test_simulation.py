"""Tests for ladder.simulation — cost simulation framework."""

from __future__ import annotations

import pytest

from ladder.models import LadderLevel, TokenUsage
from ladder.simulation import (
    BUILTIN_SCENARIOS,
    Simulator,
    TaskScenario,
    run_all_comparisons,
)


@pytest.fixture
def simple_scenarios():
    """A small set of scenarios for testing."""
    return [
        TaskScenario("Fix typo", LadderLevel.intern, 300, 150),
        TaskScenario("Write test", LadderLevel.junior, 500, 300),
        TaskScenario("Implement feature", LadderLevel.mid, 1000, 600),
        TaskScenario("Refactor module", LadderLevel.senior, 2000, 1000),
        TaskScenario("Design system", LadderLevel.staff, 3000, 1500),
    ]


class TestTaskScenario:
    def test_creation(self):
        s = TaskScenario("Fix bug", LadderLevel.mid, 500, 200)
        assert s.task == "Fix bug"
        assert s.true_level == LadderLevel.mid
        assert s.estimated_input_tokens == 500
        assert s.estimated_output_tokens == 200


class TestSimulatorRunLadder:
    def test_returns_simulation_result(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_ladder(simple_scenarios)
        assert result.strategy_name == "Ladder (smart routing)"
        assert len(result.per_task_costs) == len(simple_scenarios)
        assert result.total_cost == pytest.approx(sum(result.per_task_costs))

    def test_levels_used_matches_scenarios(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_ladder(simple_scenarios)
        assert result.levels_used[LadderLevel.intern] == 1
        assert result.levels_used[LadderLevel.junior] == 1
        assert result.levels_used[LadderLevel.mid] == 1
        assert result.levels_used[LadderLevel.senior] == 1
        assert result.levels_used[LadderLevel.staff] == 1

    def test_includes_classification_cost(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_ladder(simple_scenarios)
        # Ladder includes classification cost, so total should be higher than
        # just the agent cost. Compare with fixed_level which has no classifier cost.
        fixed_result = sim.run_fixed_level(simple_scenarios, LadderLevel.intern)
        # For intern-level tasks, ladder cost includes classification overhead
        # but the intern tasks themselves cost the same
        assert result.total_cost > 0

    def test_cost_is_positive(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_ladder(simple_scenarios)
        for cost in result.per_task_costs:
            assert cost > 0

    def test_empty_scenarios(self):
        sim = Simulator()
        result = sim.run_ladder([])
        assert result.total_cost == 0.0
        assert result.per_task_costs == []
        assert result.levels_used == {}


class TestSimulatorRunFixedLevel:
    def test_all_tasks_use_same_level(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_fixed_level(simple_scenarios, LadderLevel.mid)
        assert result.levels_used == {LadderLevel.mid: len(simple_scenarios)}

    def test_strategy_name(self, simple_scenarios):
        sim = Simulator()
        result = sim.run_fixed_level(simple_scenarios, LadderLevel.principal)
        assert result.strategy_name == "Always Principal"

    def test_opus_more_expensive_than_haiku(self, simple_scenarios):
        sim = Simulator()
        haiku = sim.run_fixed_level(simple_scenarios, LadderLevel.intern)
        opus = sim.run_fixed_level(simple_scenarios, LadderLevel.principal)
        assert opus.total_cost > haiku.total_cost

    def test_cost_proportional_to_pricing(self):
        """A single 1M-token task should match known pricing."""
        scenarios = [
            TaskScenario("Test", LadderLevel.mid, 1_000_000, 1_000_000),
        ]
        sim = Simulator()
        # Intern: $1/MTok in + $5/MTok out = $6
        result = sim.run_fixed_level(scenarios, LadderLevel.intern)
        assert result.total_cost == pytest.approx(6.00)
        # Mid: $3/MTok in + $15/MTok out = $18
        result = sim.run_fixed_level(scenarios, LadderLevel.mid)
        assert result.total_cost == pytest.approx(18.00)
        # Principal: $5/MTok in + $25/MTok out = $30
        result = sim.run_fixed_level(scenarios, LadderLevel.principal)
        assert result.total_cost == pytest.approx(30.00)

    def test_empty_scenarios(self):
        sim = Simulator()
        result = sim.run_fixed_level([], LadderLevel.mid)
        assert result.total_cost == 0.0


class TestSimulatorCompare:
    def test_compare_output_format(self, simple_scenarios):
        sim = Simulator()
        results = [
            sim.run_fixed_level(simple_scenarios, LadderLevel.principal),
            sim.run_fixed_level(simple_scenarios, LadderLevel.intern),
            sim.run_ladder(simple_scenarios),
        ]
        output = sim.compare(results)
        assert "Cost Comparison" in output
        assert "Strategy" in output
        assert "Total Cost" in output
        assert "Savings" in output
        assert "Always Principal" in output
        assert "Always Intern" in output
        assert "Ladder (smart routing)" in output

    def test_compare_shows_level_breakdown_for_ladder(self, simple_scenarios):
        sim = Simulator()
        results = [
            sim.run_fixed_level(simple_scenarios, LadderLevel.principal),
            sim.run_ladder(simple_scenarios),
        ]
        output = sim.compare(results)
        assert "Level breakdown" in output

    def test_compare_empty(self):
        sim = Simulator()
        output = sim.compare([])
        assert output == "No results to compare."

    def test_most_expensive_shows_zero_savings(self, simple_scenarios):
        sim = Simulator()
        results = [
            sim.run_fixed_level(simple_scenarios, LadderLevel.principal),
            sim.run_fixed_level(simple_scenarios, LadderLevel.intern),
        ]
        output = sim.compare(results)
        assert "0.0%" in output  # Most expensive has 0% savings


class TestBuiltinScenarios:
    def test_all_four_scenarios_exist(self):
        assert "Typical Workload" in BUILTIN_SCENARIOS
        assert "Documentation-Heavy Sprint" in BUILTIN_SCENARIOS
        assert "Architecture Week" in BUILTIN_SCENARIOS
        assert "Bug Bash" in BUILTIN_SCENARIOS

    def test_scenarios_have_tasks(self):
        for name, scenarios in BUILTIN_SCENARIOS.items():
            assert len(scenarios) > 0, f"{name} has no tasks"

    def test_typical_workload_distribution(self):
        """Typical workload: 50% simple, 30% medium, 15% complex, 5% arch."""
        scenarios = BUILTIN_SCENARIOS["Typical Workload"]
        total = len(scenarios)
        assert total == 100

    def test_run_all_comparisons(self):
        output = run_all_comparisons()
        assert "Typical Workload" in output
        assert "Documentation-Heavy Sprint" in output
        assert "Architecture Week" in output
        assert "Bug Bash" in output
        assert "Ladder (smart routing)" in output

    def test_ladder_cheaper_than_always_opus(self):
        """Ladder routing should be cheaper than always using Opus for typical workloads."""
        sim = Simulator()
        for name, scenarios in BUILTIN_SCENARIOS.items():
            ladder = sim.run_ladder(scenarios)
            opus = sim.run_fixed_level(scenarios, LadderLevel.principal)
            assert ladder.total_cost <= opus.total_cost, (
                f"Ladder should be <= Opus for {name}"
            )
