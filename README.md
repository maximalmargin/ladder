# Ladder

Software engineering agent harness that routes tasks to the right Claude model tier based on complexity — optimizing LLM costs without sacrificing quality.

Simple tasks (fix a typo, add a docstring) go to cheap/fast models. Complex tasks (system design, architecture) go to powerful ones. A lightweight classifier decides where each task lands.

## How It Works

```
Task → Classifier (Haiku) → Route to level → Agent responds
                                    ↓ (if needed)
                              Escalate to next level
```

1. **Classify** — Haiku analyzes the task and assigns a career-ladder level
2. **Route** — The task runs on the model/budget for that level
3. **Escalate** — If the agent recognizes it's out of its depth, it passes the task up (max 3 times)

Low classifier confidence (< 0.7) pre-emptively bumps the task one level to avoid wasting a cheap call.

## Levels

| Level | Model | Max Tokens | Input $/MTok | Output $/MTok |
|---|---|---|---|---|
| Intern | Haiku 4.5 | 2,048 | $1.00 | $5.00 |
| Junior | Haiku 4.5 | 4,096 | $1.00 | $5.00 |
| Mid | Sonnet 4.5 | 8,192 | $3.00 | $15.00 |
| Senior | Sonnet 4.5 | 16,384 | $3.00 | $15.00 |
| Staff | Opus 4.6 | 32,768 | $5.00 | $25.00 |
| Principal | Opus 4.6 | 65,536 | $5.00 | $25.00 |

Adjacent levels share the same model but differ in system prompt scope and token budget.

## Installation

```bash
pip install -e .
```

Requires Python 3.11+ and an `ANTHROPIC_API_KEY` environment variable.

## Usage

```bash
# Submit a task
ladder run "Add a docstring to this function"

# Verbose mode — shows classification, routing, and cost breakdown
ladder run -v "Design a microservices migration strategy"

# Read task from file
ladder run -f task.txt

# Show all level configurations
ladder levels
```

## Python API

```python
import asyncio
from ladder import Orchestrator

async def main():
    orchestrator = Orchestrator()
    result = await orchestrator.run("Refactor this module to use dependency injection")
    print(result.response)
    print(f"Level: {result.final_level.value}, Cost: ${result.total_cost_usd:.6f}")

asyncio.run(main())
```

## Project Structure

```
src/ladder/
  models.py         # Pydantic data models & enums
  levels.py         # Level configs (model, tokens, pricing)
  prompts.py        # System prompts per level + classifier prompt
  cost.py           # Token-to-USD cost calculation
  classifier.py     # Haiku-based task complexity classifier
  agent.py          # Agent wrapper per ladder level
  orchestrator.py   # Main harness: classify → route → escalate
  cli.py            # Click CLI entry point
```
