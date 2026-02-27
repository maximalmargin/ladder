# Ladder + OpenClaw Integration Plan

## What is OpenClaw?

[OpenClaw](https://github.com/openclaw/openclaw) (formerly Moltbot/Clawdbot) is an open-source, self-hosted personal AI assistant created by Peter Steinberger. It has 68k+ GitHub stars and is one of the most popular AI agent platforms in 2026.

**Core architecture:**

- **Gateway** -- a WebSocket-based control plane (`ws://127.0.0.1:18789`) that manages sessions, channels, tools, and events
- **Pi Agent Runtime** -- executes agent logic with RPC mode, tool calling, and block streaming
- **Multi-channel routing** -- connects to WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Google Chat, Microsoft Teams, and more
- **Docker sandbox** -- per-session containers for safe code execution
- **Skills system** -- extensible capabilities via `SKILL.md` files with YAML frontmatter

**Model provider system:**

OpenClaw is model-agnostic. Models are referenced as `provider/model` (e.g., `anthropic/claude-opus-4-6`). Configuration lives in `~/.openclaw/openclaw.json`:

```jsonc
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-opus-4-6",
        "fallbacks": ["openai/gpt-5.2"]
      },
      "heartbeat": { "model": "google/gemini-2.5-flash-lite" },
      "subagents": { "model": "deepseek/deepseek-reasoner" }
    }
  },
  "models": {
    "providers": {
      "custom-name": {
        "baseUrl": "https://api.example.com/v1",
        "apiKey": "${API_KEY}",
        "api": "anthropic-messages",
        "models": [{ "id": "model-id", "name": "Display Name" }]
      }
    }
  }
}
```

Custom providers support `openai-completions` and `anthropic-messages` API types.

**Why OpenClaw needs ladder:**

OpenClaw users face a real cost problem. A [VelvetShark analysis](https://velvetshark.com/openclaw-multi-model-routing) showed power users spending $943/month because every action -- heartbeats, calendar lookups, complex reasoning -- hits the same expensive model. Manual model tiering can cut costs 65%, but requires users to configure everything by hand. Ladder automates this with intelligent, per-task classification.

---

## Integration Architecture

Three integration strategies, from simplest to most powerful:

### Strategy 1: OpenClaw Skill (Recommended First Step)

Create a custom OpenClaw skill that exposes ladder as a tool the agent can invoke for task routing decisions.

```
~/.openclaw/skills/ladder/
  SKILL.md       # Skill definition + agent instructions
  server.py      # Lightweight HTTP wrapper around ladder
```

**How it works:** The OpenClaw agent receives a user message. The ladder skill's instructions tell the agent to classify tasks through ladder before executing them, then use the recommended model tier. The agent can switch models mid-session via `/model` commands informed by ladder's classification.

**Pros:** Zero changes to OpenClaw core. Uses existing skill system. Easy to install and share via ClawHub.

**Cons:** Advisory only -- the agent decides whether to follow ladder's recommendation. No automatic model switching.

### Strategy 2: Proxy Model Provider (Most Impactful)

Run ladder as an Anthropic-compatible API proxy that OpenClaw connects to as a custom model provider. Ladder intercepts every request, classifies the task, and routes to the appropriate Claude tier.

```
OpenClaw Gateway
    ↓ (all LLM requests)
Ladder Proxy (localhost:8420)
    ↓ classify_task()
    ↓ route to tier
    ├── Haiku  (intern/junior tasks)
    ├── Sonnet (mid/senior tasks)
    └── Opus   (staff/principal tasks)
```

**How it works:** OpenClaw is configured with a single custom provider pointing at ladder's proxy. Ladder receives every request, classifies it, and forwards to the appropriate Claude model. OpenClaw sees a single provider; ladder handles all routing transparently.

**Pros:** Fully automatic. No agent cooperation needed. Every LLM call is cost-optimized. Works with heartbeats, subagents, and all OpenClaw subsystems.

**Cons:** Adds latency (classification step). Requires running the proxy alongside OpenClaw.

### Strategy 3: OpenClaw Plugin (Deep Integration)

Build an OpenClaw plugin (`openclaw.plugin.json`) that patches the model selection layer directly.

**Pros:** Tightest integration. Can access OpenClaw session context for better classification.

**Cons:** Depends on OpenClaw internals. Higher maintenance burden. Plugin API may change.

---

## Detailed Design: Strategy 2 (Proxy Model Provider)

This is the highest-impact approach and the recommended primary investment.

### Proxy Server

A new module `ladder.proxy` exposes ladder as an Anthropic Messages API-compatible HTTP server:

```python
# src/ladder/proxy.py
from aiohttp import web
from anthropic import AsyncAnthropic
from ladder import Orchestrator, classify_task, LadderLevel
from ladder.levels import LEVEL_CONFIGS

# Map ladder levels to Claude model IDs
LEVEL_TO_MODEL = {
    LadderLevel.intern:    "claude-haiku-4-5-20251001",
    LadderLevel.junior:    "claude-haiku-4-5-20251001",
    LadderLevel.mid:       "claude-sonnet-4-5-20250929",
    LadderLevel.senior:    "claude-sonnet-4-5-20250929",
    LadderLevel.staff:     "claude-opus-4-6",
    LadderLevel.principal: "claude-opus-4-6",
}

client = AsyncAnthropic()

async def handle_messages(request: web.Request) -> web.Response:
    """Anthropic Messages API-compatible endpoint with ladder routing."""
    body = await request.json()

    # Extract the task text from the last user message
    messages = body.get("messages", [])
    task_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            task_text = content if isinstance(content, str) else str(content)
            break

    # Classify via ladder (uses Haiku -- cheap)
    classification = await classify_task(client, task_text)

    # Route to appropriate model
    target_model = LEVEL_TO_MODEL[classification.level]
    level_config = LEVEL_CONFIGS[classification.level]

    # Override model and max_tokens in the request
    body["model"] = target_model
    if "max_tokens" not in body:
        body["max_tokens"] = level_config.max_output_tokens

    # Forward to Anthropic API
    response = await client.messages.create(**body)

    # Add ladder metadata to response headers
    headers = {
        "X-Ladder-Level": classification.level.value,
        "X-Ladder-Category": classification.category.value,
        "X-Ladder-Confidence": str(classification.confidence),
        "X-Ladder-Model": target_model,
    }

    return web.json_response(response.model_dump(), headers=headers)


app = web.Application()
app.router.add_post("/v1/messages", handle_messages)

def main():
    web.run_app(app, host="127.0.0.1", port=8420)
```

### OpenClaw Configuration

```jsonc
// ~/.openclaw/openclaw.json
{
  "models": {
    "providers": {
      "ladder": {
        "baseUrl": "http://127.0.0.1:8420/v1",
        "apiKey": "${ANTHROPIC_API_KEY}",
        "api": "anthropic-messages",
        "models": [
          {
            "id": "ladder-auto",
            "name": "Ladder Auto-Router",
            "contextWindow": 200000,
            "maxTokens": 65536
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ladder/ladder-auto"
      }
    }
  }
}
```

### CLI Extension

```bash
# Start the proxy
ladder proxy                    # Default: 127.0.0.1:8420
ladder proxy --port 9000        # Custom port
ladder proxy --verbose          # Log every classification decision
```

---

## Detailed Design: Strategy 1 (OpenClaw Skill)

### Skill Definition

```markdown
<!-- ~/.openclaw/skills/ladder/SKILL.md -->
---
name: ladder
description: Cost-optimized model routing for Claude. Classifies tasks by complexity and recommends the cheapest capable model tier.
user-invocable: true
metadata: {"openclaw":{"requires":{"bins":["ladder"],"env":["ANTHROPIC_API_KEY"]},"emoji":"🪜"}}
---

# Ladder -- LLM Cost Optimizer

You have access to the `ladder` CLI tool for classifying task complexity.

## When to use

Before starting any significant task, run ladder to determine the optimal model tier:

```bash
ladder classify "description of the task"
```

This returns a JSON classification:
- **level**: intern/junior/mid/senior/staff/principal
- **model**: recommended Claude model
- **confidence**: 0.0-1.0 classification confidence
- **category**: code_review/implementation/debugging/testing/architecture/documentation/refactoring

## How to act on results

- If the current model is more expensive than recommended, suggest switching: `/model [recommended-alias]`
- If the task requires a more powerful model than the current one, escalate
- Always mention the cost savings to the user

## Do NOT use ladder for

- Heartbeat checks (always use cheapest model)
- Simple confirmations or acknowledgments
- Tasks already in progress
```

### Classify Subcommand

Add a `ladder classify` CLI command that outputs JSON for machine consumption:

```python
# Addition to src/ladder/cli.py

@cli.command()
@click.argument("task")
def classify(task: str):
    """Classify a task and output routing recommendation as JSON."""
    import json

    result = asyncio.run(_classify(task))
    output = {
        "level": result.level.value,
        "category": result.category.value,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "estimated_complexity": result.estimated_complexity,
        "recommended_model": LEVEL_TO_MODEL[result.level],
    }
    click.echo(json.dumps(output, indent=2))
```

---

## Implementation Steps

### Phase 1: Foundation (Week 1)

1. **Add `ladder classify` CLI command** -- JSON output for machine consumption
2. **Add `ladder.proxy` module** -- Anthropic Messages API-compatible HTTP proxy
3. **Add `ladder proxy` CLI command** -- starts the proxy server
4. **Write tests** for proxy routing logic (mock Anthropic API, verify model selection)

### Phase 2: OpenClaw Skill (Week 2)

5. **Create the skill directory** with `SKILL.md`
6. **Test with a local OpenClaw instance** -- verify skill loads and agent follows recommendations
7. **Package for ClawHub** distribution

### Phase 3: Proxy Hardening (Week 3)

8. **Streaming support** -- proxy must handle SSE streaming responses from Anthropic API
9. **Request caching** -- cache classification results for identical/similar prompts within a session
10. **Cost dashboard** -- add `/stats` endpoint showing cumulative savings vs. single-model baseline
11. **Configurable overrides** -- allow users to pin specific task types to specific models

### Phase 4: Polish & Launch (Week 4)

12. **Documentation** -- README section, OpenClaw setup guide, troubleshooting
13. **Docker Compose** -- single-command setup: `docker compose up` starts ladder proxy + OpenClaw
14. **Publish** -- PyPI package update, ClawHub skill listing, blog post / announcement

### Dependencies

New Python dependencies for the proxy:

```toml
# pyproject.toml additions
[project.optional-dependencies]
proxy = ["aiohttp>=3.9"]

[project.scripts]
ladder = "ladder.cli:cli"
```

---

## Cost Savings Projection

Based on the [VelvetShark analysis](https://velvetshark.com/openclaw-multi-model-routing) of OpenClaw usage patterns:

| Scenario | Without Ladder | With Ladder | Savings |
|----------|---------------|-------------|---------|
| Light (20 tasks/day) | $200/mo | $55/mo | **72%** |
| Power (50 tasks/day) | $943/mo | $240/mo | **75%** |
| Heavy (parallel agents) | $2,750/mo | $680/mo | **75%** |

Ladder improves on manual tiering because:
- Classification is automatic (no user effort)
- Per-task granularity (not per-session)
- Confidence-based escalation catches edge cases
- Cost tracking provides visibility

---

## Open Questions

1. **Streaming** -- OpenClaw relies heavily on streaming responses. The proxy must support SSE pass-through. Should ladder classify before streaming starts (adds latency) or stream from a default model and reclassify for next turn?

2. **Context window** -- OpenClaw sends full conversation history. Long contexts may need Sonnet/Opus regardless of task simplicity. Should ladder factor message count / token count into routing?

3. **Tool calls** -- OpenClaw uses extensive tool calling. Some models handle tools better than others. Should ladder bias toward Sonnet+ when tool_use is detected in the request?

4. **Heartbeat optimization** -- OpenClaw heartbeats run every 30 minutes and are trivially simple. The proxy should fast-path these to Haiku without classification overhead.

5. **Multi-agent** -- OpenClaw supports spawning subagents. Should each subagent get independent classification, or inherit the parent's level?
