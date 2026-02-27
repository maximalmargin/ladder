"""Tests for ladder.cost — cost calculation and formatting."""

from __future__ import annotations

import pytest

from ladder.cost import calculate_cost, format_cost_summary
from ladder.models import CostRecord, LadderLevel, TokenUsage


class TestCalculateCost:
    def test_intern_cost(self):
        """Intern (Haiku): $1.00/MTok input, $5.00/MTok output."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.intern, usage)
        assert record.cost_usd == pytest.approx(6.00)  # 1.00 + 5.00

    def test_junior_cost(self):
        """Junior (Haiku): same pricing as intern."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.junior, usage)
        assert record.cost_usd == pytest.approx(6.00)

    def test_mid_cost(self):
        """Mid (Sonnet): $3.00/MTok input, $15.00/MTok output."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.mid, usage)
        assert record.cost_usd == pytest.approx(18.00)  # 3.00 + 15.00

    def test_senior_cost(self):
        """Senior (Sonnet): same pricing as mid."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.senior, usage)
        assert record.cost_usd == pytest.approx(18.00)

    def test_staff_cost(self):
        """Staff (Opus): $5.00/MTok input, $25.00/MTok output."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.staff, usage)
        assert record.cost_usd == pytest.approx(30.00)  # 5.00 + 25.00

    def test_principal_cost(self):
        """Principal (Opus): same pricing as staff."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.principal, usage)
        assert record.cost_usd == pytest.approx(30.00)

    def test_small_token_counts(self):
        """Test with realistic small token counts."""
        usage = TokenUsage(input_tokens=500, output_tokens=200)
        record = calculate_cost(LadderLevel.mid, usage)
        # (500 / 1M) * 3.00 + (200 / 1M) * 15.00 = 0.0015 + 0.003 = 0.0045
        assert record.cost_usd == pytest.approx(0.0045)

    def test_zero_tokens(self):
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        record = calculate_cost(LadderLevel.staff, usage)
        assert record.cost_usd == 0.0

    def test_large_token_counts(self):
        """Test with very large token counts."""
        usage = TokenUsage(input_tokens=10_000_000, output_tokens=5_000_000)
        record = calculate_cost(LadderLevel.principal, usage)
        # (10M / 1M) * 5.00 + (5M / 1M) * 25.00 = 50.00 + 125.00 = 175.00
        assert record.cost_usd == pytest.approx(175.00)

    def test_input_only(self):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=0)
        record = calculate_cost(LadderLevel.mid, usage)
        assert record.cost_usd == pytest.approx(3.00)

    def test_output_only(self):
        usage = TokenUsage(input_tokens=0, output_tokens=1_000_000)
        record = calculate_cost(LadderLevel.mid, usage)
        assert record.cost_usd == pytest.approx(15.00)

    def test_record_fields(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        record = calculate_cost(LadderLevel.senior, usage, description="My call")
        assert record.level == LadderLevel.senior
        assert record.usage is usage
        assert record.description == "My call"

    def test_description_default(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        record = calculate_cost(LadderLevel.intern, usage)
        assert record.description == ""


class TestFormatCostSummary:
    def test_empty_records(self):
        assert format_cost_summary([]) == "No API calls made."

    def test_single_record(self):
        records = [
            CostRecord(
                level=LadderLevel.mid,
                usage=TokenUsage(input_tokens=500, output_tokens=200),
                cost_usd=0.0045,
                description="Classification",
            )
        ]
        output = format_cost_summary(records)
        assert "Cost Breakdown:" in output
        assert "Classification" in output
        assert "$0.004500" in output
        assert "500in/200out" in output
        assert "mid" in output
        assert "Total: $0.004500" in output

    def test_multiple_records(self):
        records = [
            CostRecord(
                level=LadderLevel.intern,
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                cost_usd=0.00035,
                description="Classification",
            ),
            CostRecord(
                level=LadderLevel.mid,
                usage=TokenUsage(input_tokens=500, output_tokens=200),
                cost_usd=0.0045,
                description="Agent (mid)",
            ),
        ]
        output = format_cost_summary(records)
        assert "Classification" in output
        assert "Agent (mid)" in output
        total = 0.00035 + 0.0045
        assert f"Total: ${total:.6f}" in output

    def test_record_without_description_uses_call_number(self):
        records = [
            CostRecord(
                level=LadderLevel.intern,
                usage=TokenUsage(input_tokens=10, output_tokens=5),
                cost_usd=0.0001,
                description="",
            )
        ]
        output = format_cost_summary(records)
        assert "Call 1" in output

    def test_separator_lines(self):
        records = [
            CostRecord(
                level=LadderLevel.intern,
                usage=TokenUsage(),
                cost_usd=0.0,
                description="test",
            )
        ]
        output = format_cost_summary(records)
        lines = output.split("\n")
        assert lines[1] == "-" * 50
        assert lines[-2] == "-" * 50
