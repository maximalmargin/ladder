"""Click CLI entry point for the ladder harness."""

from __future__ import annotations

import asyncio
import sys

import click

from .cost import format_cost_summary
from .levels import LEVEL_CONFIGS
from .orchestrator import Orchestrator


@click.group()
def main() -> None:
    """Ladder: Software engineering agent harness for cost-optimized LLM routing."""


@main.command()
@click.argument("task", required=False)
@click.option("-v", "--verbose", is_flag=True, help="Show classification and cost details")
@click.option("-f", "--file", "task_file", type=click.Path(exists=True), help="Read task from file")
def run(task: str | None, verbose: bool, task_file: str | None) -> None:
    """Submit a task to the ladder harness."""
    if task_file:
        with open(task_file) as f:
            task_text = f.read().strip()
    elif task:
        task_text = task
    else:
        click.echo("Error: Provide a task as an argument or via -f/--file.", err=True)
        sys.exit(1)

    result = asyncio.run(_run_task(task_text, verbose))

    if verbose:
        click.echo(f"\nClassification:")
        click.echo(f"  Level: {result.classification.level.value}")
        click.echo(f"  Category: {result.classification.category.value}")
        click.echo(f"  Confidence: {result.classification.confidence:.2f}")
        click.echo(f"  Complexity: {result.classification.estimated_complexity}/10")
        click.echo(f"  Reasoning: {result.classification.reasoning}")
        click.echo(f"\nRouting:")
        click.echo(f"  Initial level: {result.initial_level.value}")
        click.echo(f"  Final level: {result.final_level.value}")
        if result.escalations:
            click.echo(f"  Escalations: {', '.join(e.value for e in result.escalations)}")
        click.echo()

    click.echo(result.response)

    if verbose:
        click.echo()
        click.echo(format_cost_summary(result.costs))


async def _run_task(task: str, verbose: bool) -> object:
    """Run a task through the orchestrator."""
    orchestrator = Orchestrator()
    return await orchestrator.run(task)


@main.command()
def levels() -> None:
    """Show all ladder level configurations."""
    click.echo("Ladder Levels:")
    click.echo("=" * 70)
    for level, config in LEVEL_CONFIGS.items():
        click.echo(f"\n  {level.value.upper()}")
        click.echo(f"    Model:       {config.model_id}")
        click.echo(f"    Max tokens:  {config.max_output_tokens:,}")
        click.echo(f"    Input cost:  ${config.pricing.input_per_mtok:.2f}/MTok")
        click.echo(f"    Output cost: ${config.pricing.output_per_mtok:.2f}/MTok")
        click.echo(f"    Description: {config.description}")
    click.echo()
