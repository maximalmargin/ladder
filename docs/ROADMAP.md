# Ladder Roadmap

> Where we're going and why. This document outlines the evolution of Ladder from a focused cost-optimization harness into a full platform for intelligent LLM routing.

---

## Design Principles

These principles guide every feature decision. When in doubt, refer back here.

**1. Cheapest correct answer wins.**
The entire point of Ladder is that most tasks don't need the most expensive model. Every feature should either reduce cost, improve routing accuracy, or make it easier to verify that the cheap answer was good enough.

**2. Classification is the bottleneck, not generation.**
A misrouted task wastes more money than a slightly slower classifier. Invest heavily in classification quality — it's the lever with the highest ROI.

**3. Escalation is not failure.**
Escalation is the safety net that makes aggressive cost optimization possible. A system that never escalates is over-spending. A system that always escalates is broken. The sweet spot is ~10-15% escalation rate.

**4. Observe everything, require nothing.**
Every API call, routing decision, escalation, and cost should be observable. But the default experience should be zero-config: `pip install ladder` and go.

**5. Provider-agnostic where possible, Claude-optimized where it matters.**
The routing and classification logic should generalize. The prompt engineering and escalation protocol are Claude-specific and that's fine — they're the secret sauce.

**6. Composition over configuration.**
Prefer composable primitives (agents, classifiers, cost calculators) over a single monolith with a hundred config knobs. Users should be able to swap parts without understanding the whole.

**7. Fail fast, fail cheap.**
If something is going to fail, it should fail at the cheapest model tier, not after burning through an Opus call. Validate early, escalate deliberately.

---

## Current Architecture (v0.1.0)

For context, here's what exists today:

```
Task → Classifier (Haiku) → Route to level → Agent responds
                                    ↓ (if needed)
                              Escalate to next level (up to 3x)
```

**Modules:** `models.py` (Pydantic data models), `levels.py` (6-tier config: intern→principal), `prompts.py` (per-level system prompts + classifier prompt), `cost.py` (token→USD calculation), `classifier.py` (Haiku-based structured output), `agent.py` (level-bound agent wrapper), `orchestrator.py` (classify→route→escalate loop), `cli.py` (Click CLI).

**Key numbers:** 6 levels, 3 models (Haiku/Sonnet/Opus), max 3 escalations, 0.7 confidence threshold, ~$1-25/MTok range.

---

## Phase 1: Foundation (Quick Wins)

Low-risk improvements that build on the existing architecture without structural changes. Target: weeks, not months.

### 1.1 Streaming Support

**Description:** Yield response chunks from the agent as they arrive instead of waiting for the full response. The Anthropic SDK already supports streaming via `client.messages.stream()` — this is mostly a plumbing change through `LadderAgent.run()` and the orchestrator.

**Complexity:** S
**Impact:** High UX improvement — users see output immediately instead of staring at a blank terminal. Critical for CLI adoption.

**Key technical considerations:**
- `LadderAgent.run()` needs a `stream=True` variant returning an `AsyncIterator[str]`
- Escalation detection becomes harder — currently checks the full response text for `ESCALATE:` prefix. With streaming, need to buffer the first few tokens or switch to a structured stop-reason approach
- The orchestrator's escalation loop needs to handle the case where streaming started but then needs to be abandoned for escalation
- Cost tracking: token counts come from the final `message_stop` event, not mid-stream
- CLI can use `click.echo()` per chunk; Python API returns an async generator

### 1.2 Error Handling and Retries

**Description:** Add retry logic for transient API failures (rate limits, 5xx errors, timeouts) with exponential backoff. Currently, a single failed API call crashes the entire pipeline.

**Complexity:** S
**Impact:** High reliability — production systems need this. Without retries, a single 429 kills the run.

**Key technical considerations:**
- Use `tenacity` or build a simple retry decorator — the Anthropic SDK has some built-in retry support via `max_retries` on the client constructor, but we need more control
- Retry budget: classify retries separately from agent retries. A flaky classifier shouldn't exhaust the retry budget meant for the agent
- Idempotency: our API calls are naturally idempotent (same prompt → same-ish response), so retries are safe
- Surface retry counts in `CostRecord` or a new `RunMetadata` model so users know retries happened
- Consider a circuit breaker pattern for sustained failures — if Haiku is down, maybe skip classification and default to Sonnet

### 1.3 Logging and Observability

**Description:** Add structured logging throughout the pipeline using Python's `logging` module. Emit events for: classification result, routing decision, escalation trigger, API call timing, cost per call, and total cost.

**Complexity:** S
**Impact:** Medium — essential for debugging and cost auditing in production. Users currently have no visibility into *why* a task was routed where it was unless they use `-v`.

**Key technical considerations:**
- Use `structlog` or standard `logging` with JSON formatter for machine-parseable output
- Define a clear event schema: `{"event": "classification", "level": "mid", "confidence": 0.85, "latency_ms": 230, ...}`
- Add optional OpenTelemetry span support for distributed tracing (don't make it a hard dependency)
- Log levels: DEBUG for raw API responses, INFO for routing decisions, WARNING for escalations and retries, ERROR for failures
- The CLI's `--verbose` flag should map to setting log level to DEBUG
- Consider a callback/hook system: `orchestrator.on_classify`, `orchestrator.on_escalate`, etc.

### 1.4 Configuration File Support (ladder.toml)

**Description:** Allow users to override defaults (confidence threshold, max escalations, model overrides, pricing) via a `ladder.toml` file. Discover it by walking up from CWD, similar to how `pyproject.toml` is found.

**Complexity:** M
**Impact:** Medium — enables teams to standardize settings without code changes. Unlocks use cases like "always use Sonnet for our repo because our codebase is complex."

**Key technical considerations:**
- Use `tomllib` (stdlib in 3.11+) — no new dependency needed
- Config schema:
  ```toml
  [ladder]
  confidence_threshold = 0.8
  max_escalations = 2

  [ladder.levels.intern]
  model_id = "claude-haiku-4-5-20251001"
  max_output_tokens = 4096

  [ladder.levels.mid]
  model_id = "claude-sonnet-4-5-20250929"
  ```
- Merge order: hardcoded defaults → `ladder.toml` → environment variables → CLI flags
- Validate config with Pydantic — reject unknown keys, type-check values
- The `LEVEL_CONFIGS` dict in `levels.py` needs to become mutable or replaced with a config-aware accessor
- Support `LADDER_CONFIG` env var pointing to an explicit config path

### 1.5 Token Counting and Cost Estimation

**Description:** Before making an API call, estimate the input token count using `anthropic.count_tokens()` or a local tokenizer. Show the user an estimated cost range before the call happens. Useful for budget-conscious teams.

**Complexity:** M
**Impact:** Medium cost visibility — users can see "this will cost ~$0.003" before committing. Enables pre-flight budget checks.

**Key technical considerations:**
- The Anthropic SDK provides token counting via `client.count_tokens()` — check if it supports async
- Alternatively, use `tiktoken` or the `anthropic-tokenizer` for local counting (faster, no API call)
- Output tokens can only be estimated heuristically — use the `max_output_tokens` config as the upper bound and historical averages as the expected value
- Add a `--dry-run` CLI flag that classifies and shows the estimated cost without actually running the agent
- Add an `estimate_cost()` method to the orchestrator that returns a cost range `(min, expected, max)` based on the classification
- Consider a pre-flight budget check: if estimated cost exceeds a user-configured threshold, prompt for confirmation

---

## Phase 2: Intelligence

Make the routing smarter over time by learning from outcomes. This is where Ladder goes from "static rules" to "adaptive system."

### 2.1 Escalation Pattern Tracking

**Description:** Log every escalation event with context (task text, initial level, final level, escalation reason) to a local SQLite database. Analyze patterns to identify systematic misclassifications — e.g., "refactoring tasks are classified as `mid` but always escalate to `senior`."

**Complexity:** M
**Impact:** High cost savings — fixing systematic misclassifications directly reduces wasted API calls. A task that always escalates from Haiku to Sonnet is paying for Haiku + Sonnet instead of just Sonnet.

**Key technical considerations:**
- SQLite is the right choice — zero-config, ships with Python, handles concurrent reads fine
- Schema: `escalations(id, timestamp, task_hash, task_category, initial_level, final_level, escalation_reasons, confidence, task_text_preview)`
- Privacy: store a hash of the task text, not the full text, by default. Offer an opt-in full-text mode
- Periodically generate a "misclassification report" showing categories with high escalation rates
- This data feeds directly into classifier fine-tuning (Phase 2.4) and dynamic thresholds (Phase 2.3)
- Keep the storage layer pluggable — SQLite locally, but PostgreSQL or cloud storage for teams

### 2.2 Response Quality Scoring

**Description:** After the agent responds, run a lightweight quality check: did the response actually address the task? Was the chosen level appropriate? This can be as simple as a Haiku call that scores the response on a 1-5 scale, or as sophisticated as comparing against a known-good response.

**Complexity:** L
**Impact:** High — closes the feedback loop. Without quality scoring, you only know if a task was *too hard* (escalation), never if it was *too easy* (wasted money on Opus for a docstring fix).

**Key technical considerations:**
- The quality scorer should itself be cheap — always run on Haiku to avoid defeating the cost savings
- Score dimensions: correctness, completeness, level-appropriateness (was this task harder/easier than the level suggests?)
- Store scores in the same SQLite database as escalation data
- Use quality scores to detect "over-routing": tasks that get routed to Opus but score as trivially easy
- Careful with the meta-problem: scoring costs tokens too. Only score a sample (e.g., 10%) in production, or let users opt in
- Quality scoring enables A/B testing: try the same task at two levels and compare scores

### 2.3 Dynamic Confidence Thresholds

**Description:** Instead of a global 0.7 confidence threshold, learn per-category thresholds from historical data. If `refactoring` tasks with confidence > 0.6 never escalate, lower the threshold for that category. If `architecture` tasks with confidence < 0.9 always escalate, raise it.

**Complexity:** M
**Impact:** Medium cost savings — fine-tunes the biggest lever in the system (the confidence-based bump) per category instead of using a one-size-fits-all number.

**Key technical considerations:**
- Requires Phase 2.1 (escalation tracking) as a prerequisite — need historical data
- Start with a simple heuristic: threshold = 1 - (success_rate_at_initial_level) for each category
- Store thresholds in a config that updates periodically (not on every request — that's noisy)
- Add guardrails: thresholds can't go below 0.5 or above 0.95 to prevent degenerate behavior
- The orchestrator's confidence check in `run()` needs to read from a threshold map instead of a constant
- Expose the learned thresholds via CLI (`ladder thresholds`) for visibility

### 2.4 Classifier Fine-Tuning

**Description:** Use accumulated escalation and quality data to improve the classifier over time. This could mean: (a) few-shot examples injected into the classifier prompt, (b) fine-tuning a custom Haiku model, or (c) training a local lightweight model (e.g., a scikit-learn classifier on task embeddings).

**Complexity:** XL
**Impact:** Very high — a better classifier is the single highest-leverage improvement. Even a 5% improvement in classification accuracy can save significant money at scale.

**Key technical considerations:**
- Start with few-shot examples (cheapest to implement): pick the 10 most commonly misclassified tasks and add them to `CLASSIFIER_PROMPT` as examples
- Few-shot example selection: use the escalation database to find tasks where initial_level != final_level, and include the correct level
- Fine-tuning a custom model requires Anthropic's fine-tuning API (check availability) or a third-party solution
- The local model approach is interesting for latency: a local classifier (even with lower accuracy) could pre-filter obvious cases, using Haiku only for ambiguous ones
- Evaluation: need a held-out test set of tasks with known-good levels. Bootstrap this from escalation data
- Retraining cadence: weekly or on-demand, not continuous (too much drift risk)

### 2.5 Caching Layer

**Description:** Cache responses for identical or near-identical tasks. An exact-match cache (task hash → response) handles repeated tasks. A semantic cache (task embedding → nearest neighbor) handles paraphrased tasks.

**Complexity:** L
**Impact:** High cost savings for repetitive workloads — CI/CD pipelines, code review bots, and batch processing often re-submit similar tasks.

**Key technical considerations:**
- Exact-match cache: simple dict or SQLite keyed on `hash(task_text + context)`. High precision, low recall
- Semantic cache: embed tasks using a small model, store in a vector DB (FAISS, ChromaDB), retrieve nearest neighbors above a similarity threshold. Higher recall, risk of false matches
- Cache invalidation: LLM responses aren't deterministic, and the "correct" answer can change as code evolves. Use TTLs (e.g., 1 hour for code review, 24 hours for documentation)
- Cache key should include the level — a cached Haiku response shouldn't be returned when Opus is requested
- Cost tracking: cached responses should show $0 cost but still appear in the cost breakdown
- Start with exact-match only — it's simple and handles the most common case (re-runs during development)

---

## Phase 3: Multi-Provider

Break free from Anthropic-only. Support routing across providers for cost arbitrage, redundancy, and capability matching.

### 3.1 Multi-Provider Model Support

**Description:** Add support for OpenAI (GPT-4o, GPT-4o-mini, o3-mini), Google (Gemini 2.0 Flash, Gemini 2.0 Pro), and open-source models (Llama, Mixtral via Ollama/vLLM). Each provider has its own SDK, auth, and response format — abstract behind a common interface.

**Complexity:** XL
**Impact:** Very high — unlocks the full cost-optimization potential. GPT-4o-mini might be cheaper than Haiku for some tasks; Gemini Flash might beat both. Provider arbitrage is the next frontier.

**Key technical considerations:**
- Define a `ModelProvider` protocol/ABC: `async def complete(system, messages, max_tokens) -> ProviderResponse`
- Implement `AnthropicProvider`, `OpenAIProvider`, `GoogleProvider`, `OllamaProvider`
- The `LevelConfig` needs to reference a provider + model instead of just a model ID
- Prompt translation: system prompts work differently across providers (some use system messages, some use the first user message). Abstract this in the provider layer
- Response parsing: escalation detection (`ESCALATE:` prefix) is prompt-engineering that may need per-provider tuning
- Auth: each provider has its own API key. Support `OPENAI_API_KEY`, `GOOGLE_API_KEY`, etc.
- The classifier should remain on Haiku (or the cheapest available model) regardless of which provider handles the task

### 3.2 Unified Pricing Abstraction

**Description:** Extend the `Pricing` dataclass and `calculate_cost()` to handle pricing from any provider. Different providers have wildly different pricing models (per-token, per-character, per-request, tiered volume discounts).

**Complexity:** M
**Impact:** Medium — accurate cross-provider cost comparison is essential for routing decisions. Without this, you can't make informed cost-quality tradeoffs.

**Key technical considerations:**
- Normalize everything to USD per million tokens for comparison, even if the underlying billing is different
- Handle edge cases: some providers charge per-character (Google), some have minimum charges per request, some have different prices for cached vs. uncached input
- Pricing data goes stale — build a mechanism to update it (config file, API fetch, or hardcoded with version bumps)
- Add a `--compare-costs` CLI mode that classifies a task and shows what each provider would charge
- Consider volume discounts and committed-use pricing for enterprise users

### 3.3 Provider Health Checks and Fallback Routing

**Description:** Monitor provider availability and latency. If the primary provider for a level is slow or down, automatically fall back to an alternative provider at the same capability tier.

**Complexity:** L
**Impact:** High reliability — no single provider should be a single point of failure. Also enables latency-based routing (use the fastest available provider).

**Key technical considerations:**
- Health check approaches: (a) periodic pings, (b) track recent error rates, (c) check provider status pages
- Fallback mapping: define equivalence classes — `{haiku-tier: [claude-haiku, gpt-4o-mini, gemini-flash], sonnet-tier: [claude-sonnet, gpt-4o, gemini-pro], ...}`
- Circuit breaker pattern: after N consecutive failures, stop trying a provider for M seconds
- Latency tracking: exponential moving average of response times per provider, route to the fastest
- Be careful with cost implications — the fallback provider might be more expensive. Let users configure whether to prefer cost or availability
- Health state should be shared across requests (in-process cache or a lightweight state file)

### 3.4 Cost-Quality Pareto Optimization

**Description:** Given a task, find the cheapest provider/model combination that meets a quality threshold. This is the "holy grail" — true multi-dimensional optimization across cost, quality, and latency.

**Complexity:** XL
**Impact:** Very high — this is the endgame for cost optimization. Instead of fixed level→model mappings, dynamically choose the best option.

**Key technical considerations:**
- Requires quality scoring (Phase 2.2) and multi-provider support (Phase 3.1) as prerequisites
- Build a quality-cost matrix: for each (task_category, model) pair, what's the expected quality score and cost?
- The optimizer selects the cheapest model where expected_quality >= user's quality threshold
- Cold start problem: no data for new models or categories. Default to conservative routing (more expensive) and learn
- This is fundamentally a contextual bandit problem — explore/exploit tradeoff between trying cheaper models and sticking with known-good ones
- Implementation: start with a simple lookup table, graduate to Thompson sampling or UCB for explore/exploit

---

## Phase 4: Platform

Transform Ladder from a CLI tool into a platform that teams and organizations can adopt.

### 4.1 Web Dashboard

**Description:** A web UI showing real-time and historical cost data: cost per task, cost by level, cost by category, escalation rates, quality scores, and savings vs. always-using-Opus baseline.

**Complexity:** L
**Impact:** High adoption — managers need to see the ROI. A dashboard showing "Ladder saved you $X this month" is the single best driver of organizational adoption.

**Key technical considerations:**
- Tech stack: FastAPI backend + lightweight frontend (htmx or React, depending on complexity)
- Data source: the SQLite database from Phase 2.1, or upgrade to PostgreSQL for multi-user
- Key charts: cost over time, cost by level breakdown (stacked bar), escalation rate trend, savings waterfall (cost if all Opus vs. actual cost)
- Real-time: WebSocket feed of live task processing for monitoring
- Auth: start with no auth (local only), add basic auth for shared deployments
- Deployment: ship as `ladder dashboard` CLI command that starts a local server, or deploy as a standalone service

### 4.2 GitHub Action

**Description:** A GitHub Action that runs Ladder on PRs for automated code review. Classifies the complexity of the diff, routes to the appropriate level, and posts review comments. The cost savings here are massive — most PR reviews are simple and don't need Opus.

**Complexity:** L
**Impact:** Very high adoption — this is the killer app for many teams. Automated code review is one of the highest-volume LLM use cases.

**Key technical considerations:**
- The Action needs to: (a) check out the PR, (b) extract the diff, (c) classify complexity, (d) run the review at the appropriate level, (e) post comments via GitHub API
- Context construction: the diff is the task, but the agent also needs repo context (file structure, related files, style guide)
- Cost cap: add a per-PR budget limit to prevent runaway costs on massive PRs
- Incremental review: only review changed files, and use caching (Phase 2.5) to avoid re-reviewing unchanged parts
- Output format: map agent responses to inline PR comments on specific lines
- Configuration via `.github/ladder.yml` in the repo

### 4.3 VS Code Extension

**Description:** A VS Code extension that integrates Ladder into the editor. Select code, right-click, and choose "Ladder: Review", "Ladder: Refactor", "Ladder: Explain". The extension classifies the task, routes it, and shows the response inline.

**Complexity:** XL
**Impact:** High UX — meets developers where they work. Reduces friction to near-zero.

**Key technical considerations:**
- Extension talks to a local Ladder server (API server mode, Phase 4.5) or directly to the Anthropic API
- Context: the extension can provide rich context (file content, imports, project structure) that the CLI can't easily gather
- Inline diff view for refactoring suggestions (like GitHub Copilot's suggestions)
- Cost display: show the cost of each operation in the status bar
- Keybindings and command palette integration
- Language: TypeScript (VS Code extension API). The Ladder core is Python, so either run a sidecar process or use the API server mode

### 4.4 Team and Org Management

**Description:** Multi-user support with team hierarchies, usage quotas, and shared configuration. Admins can set per-team budgets, enforce level caps (e.g., "interns can't use Opus"), and view aggregated usage across the org.

**Complexity:** XL
**Impact:** High for enterprise adoption — organizations won't adopt without usage controls and accountability.

**Key technical considerations:**
- User model: users belong to teams, teams belong to orgs. Each level has budget limits
- Auth: API keys per user, or integrate with SSO (Phase 5.1)
- Quota enforcement: pre-flight check before each API call. If budget exhausted, reject or downgrade
- Shared config: team-level `ladder.toml` overrides that apply to all members
- Usage reporting: aggregate costs by user, team, project, and time period
- Data store: PostgreSQL for multi-user data. SQLite won't cut it for concurrent writes

### 4.5 API Server Mode

**Description:** Run Ladder as a long-lived HTTP service (`ladder serve`) that accepts task requests via REST API. Enables integration with any language/tool, not just Python.

**Complexity:** M
**Impact:** High — unlocks integrations beyond the Python ecosystem. Any tool that can make HTTP requests can use Ladder.

**Key technical considerations:**
- Framework: FastAPI (already a common Anthropic ecosystem dependency)
- Endpoints: `POST /tasks` (submit), `GET /tasks/{id}` (status/result), `GET /costs` (summary), `GET /health`
- Streaming: Server-Sent Events (SSE) for streaming responses
- Concurrency: handle multiple concurrent requests. The Anthropic SDK is async-native, so this maps well to FastAPI
- Rate limiting: per-client rate limits to prevent abuse
- API key auth: simple bearer token auth for the Ladder server itself (separate from the Anthropic API key)
- OpenAPI spec auto-generated by FastAPI — clients can be generated for any language

### 4.6 Batch Processing

**Description:** Accept a batch of tasks, classify all of them, then schedule execution optimally. Group tasks by level to minimize context-switching overhead. Prioritize by urgency or dependency order.

**Complexity:** L
**Impact:** Medium — useful for CI/CD pipelines, bulk code review, and migration tasks that generate hundreds of sub-tasks.

**Key technical considerations:**
- Input format: JSONL file or directory of task files
- Scheduling: classify all tasks first (cheap — all on Haiku), then sort by level. Run lower-level tasks first (faster, cheaper) and parallelize within each level
- Concurrency: respect Anthropic API rate limits. Use a semaphore to cap concurrent requests
- Progress reporting: show a progress bar with ETA and running cost total
- Failure handling: if one task fails, continue with the rest. Generate a report of successes and failures
- Output: JSONL file with results, or a directory mirroring the input structure
- Cost estimation: show total estimated cost before starting the batch, with a confirmation prompt

---

## Phase 5: Enterprise

Features required for adoption by large organizations with strict compliance and operational requirements.

### 5.1 SSO and Authentication

**Description:** Integrate with enterprise identity providers (Okta, Azure AD, Google Workspace) via SAML/OIDC. Users authenticate once and get scoped access to Ladder based on their org role.

**Complexity:** XL
**Impact:** High for enterprise adoption — many organizations won't even evaluate a tool without SSO support.

**Key technical considerations:**
- Use a battle-tested auth library (e.g., `authlib` for Python, or offload to an auth proxy like OAuth2 Proxy)
- Role mapping: map IdP roles/groups to Ladder permissions (admin, user, viewer)
- Session management: JWT tokens with short expiry, refresh token rotation
- API key fallback: not all integrations (CI/CD, GitHub Action) can do SSO. Support API keys with scoped permissions
- Audit trail: every authentication event should be logged (Phase 5.2)
- Multi-tenancy: ensure complete data isolation between organizations

### 5.2 Audit Logging

**Description:** Immutable, tamper-evident log of every action: task submissions, routing decisions, escalations, cost events, configuration changes, and user access. Exportable in standard formats for compliance tools.

**Complexity:** L
**Impact:** High for regulated industries — healthcare, finance, and government clients require audit trails for AI tool usage.

**Key technical considerations:**
- Log format: structured JSON with timestamp, actor, action, resource, and outcome
- Immutability: append-only log file or database table with integrity checksums
- Retention: configurable retention period (default: 90 days). Support log rotation and archival
- Export: support common formats (JSON, CSV) and direct integration with SIEM tools (Splunk, Datadog)
- PII handling: task text may contain sensitive code or data. Support redaction policies
- Storage: local file for single-user, cloud storage (S3, GCS) for organizations
- Compliance frameworks: map log events to SOC 2, HIPAA, and FedRAMP control requirements

### 5.3 Custom Model Registries

**Description:** Allow organizations to register their own fine-tuned models or private deployments (Azure OpenAI, AWS Bedrock, self-hosted models) and slot them into the ladder at specific levels.

**Complexity:** L
**Impact:** Medium — enterprises often have existing model deployments and want to leverage Ladder's routing without migrating to public APIs.

**Key technical considerations:**
- Registry interface: define a `ModelRegistry` protocol that lists available models with their capabilities and pricing
- Built-in registries: `AnthropicRegistry`, `OpenAIRegistry`, `BedrockRegistry`, `OllamaRegistry`
- Custom registry: user provides a config mapping model names to endpoints, pricing, and capability tier
- Capability assessment: how to determine which level a custom model belongs to? Options: (a) user-declared, (b) benchmark suite, (c) sample task evaluation
- Endpoint configuration: support custom base URLs, auth headers, and response formats
- Hot-reload: registry changes should take effect without restarting the service

### 5.4 SLA-Based Routing

**Description:** Route based on latency requirements in addition to cost and quality. Some tasks need a response in < 2 seconds (interactive IDE use); others can tolerate 30+ seconds (batch review). Factor time-to-first-token and total latency into routing decisions.

**Complexity:** L
**Impact:** Medium — critical for real-time integrations (VS Code extension, chat interfaces) where Opus's higher latency is unacceptable even if it's the "right" level.

**Key technical considerations:**
- Latency profiles: track p50/p95/p99 latency per model from historical data
- Routing constraint: `max_latency_ms` parameter on task submission. If the optimal model can't meet the SLA, downgrade to a faster model
- Tradeoff transparency: when downgrading for latency, report it: "Routed to Sonnet instead of Opus to meet 3s SLA"
- Time-to-first-token vs. total latency: streaming (Phase 1.1) makes TTFT the more relevant metric for interactive use
- Geographic routing: different regions may have different latency characteristics
- Priority queues: high-SLA tasks jump the queue during rate limiting

### 5.5 Budget Alerts and Hard Caps

**Description:** Configurable budget limits at user, team, and org levels. Soft alerts at thresholds (80%, 90%) and hard caps that block further API calls when the budget is exhausted.

**Complexity:** M
**Impact:** High for enterprise adoption — organizations need spending controls. A runaway loop burning through an API budget is a real risk.

**Key technical considerations:**
- Budget periods: daily, weekly, monthly, or custom windows
- Soft alerts: webhook, email, or Slack notification when spend crosses a threshold
- Hard caps: reject new tasks with a clear error message when budget is exhausted. Option to downgrade (use a cheaper model) instead of rejecting
- Budget tracking: real-time running total, updated after each API call. Use the cost tracking from Phase 2.1
- Rollover: configurable whether unused budget rolls over to the next period
- Admin override: admins can temporarily lift caps for urgent tasks
- Pre-flight check: combined with cost estimation (Phase 1.5), show "this task will cost ~$X, leaving $Y in budget"

---

## Prioritization Matrix

| Feature | Phase | Complexity | Cost Impact | UX Impact | Adoption Impact |
|---|---|---|---|---|---|
| Streaming | 1 | S | - | High | Medium |
| Error handling/retries | 1 | S | Low | High | High |
| Logging/observability | 1 | S | - | Medium | Medium |
| Config file support | 1 | M | Low | Medium | Medium |
| Token counting/estimation | 1 | M | Medium | Medium | Low |
| Escalation tracking | 2 | M | High | Low | Low |
| Response quality scoring | 2 | L | High | Low | Low |
| Dynamic thresholds | 2 | M | Medium | Low | Low |
| Classifier fine-tuning | 2 | XL | Very High | Low | Low |
| Caching layer | 2 | L | High | Medium | Medium |
| Multi-provider support | 3 | XL | Very High | Low | High |
| Unified pricing | 3 | M | Medium | Low | Low |
| Provider health/fallback | 3 | L | Low | High | Medium |
| Pareto optimization | 3 | XL | Very High | Low | Medium |
| Web dashboard | 4 | L | - | High | High |
| GitHub Action | 4 | L | High | High | Very High |
| VS Code extension | 4 | XL | Medium | Very High | Very High |
| Team/org management | 4 | XL | Medium | Medium | High |
| API server mode | 4 | M | - | High | High |
| Batch processing | 4 | L | High | Medium | Medium |
| SSO/auth | 5 | XL | - | Medium | High |
| Audit logging | 5 | L | - | Low | High |
| Custom model registries | 5 | L | Medium | Low | Medium |
| SLA-based routing | 5 | L | Low | High | Medium |
| Budget alerts/hard caps | 5 | M | Medium | Medium | High |

---

## What We're Not Building

Equally important is what Ladder intentionally does *not* do:

- **Fine-grained prompt optimization.** Ladder routes tasks to the right model; it doesn't rewrite prompts to be cheaper. That's a different tool.
- **General-purpose agent framework.** Ladder is a routing harness, not LangChain. It doesn't manage tools, memory, or multi-turn conversations (yet).
- **Model training or evaluation.** Ladder uses models, it doesn't make them. Fine-tuning the classifier (Phase 2.4) is the exception, not the rule.
- **Billing or payment processing.** Ladder tracks costs; it doesn't charge customers. That's your business logic.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) (coming soon) for how to get involved. The best way to start is with Phase 1 features — they're small, well-scoped, and immediately useful.
