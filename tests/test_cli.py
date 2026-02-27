"""Tests for ladder.cli — Click CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from ladder.cli import main


class TestSimulateCommand:
    def test_simulate_runs(self):
        runner = CliRunner()
        result = runner.invoke(main, ["simulate"])
        assert result.exit_code == 0
        assert "Typical Workload" in result.output
        assert "Ladder (smart routing)" in result.output

    def test_simulate_shows_all_scenarios(self):
        runner = CliRunner()
        result = runner.invoke(main, ["simulate"])
        assert "Documentation-Heavy Sprint" in result.output
        assert "Architecture Week" in result.output
        assert "Bug Bash" in result.output

    def test_simulate_shows_comparison_table(self):
        runner = CliRunner()
        result = runner.invoke(main, ["simulate"])
        assert "Strategy" in result.output
        assert "Total Cost" in result.output
        assert "Savings" in result.output


class TestLevelsCommand:
    def test_levels_runs(self):
        runner = CliRunner()
        result = runner.invoke(main, ["levels"])
        assert result.exit_code == 0
        assert "INTERN" in result.output
        assert "PRINCIPAL" in result.output

    def test_levels_shows_model_ids(self):
        runner = CliRunner()
        result = runner.invoke(main, ["levels"])
        assert "claude-haiku" in result.output
        assert "claude-sonnet" in result.output
        assert "claude-opus" in result.output
