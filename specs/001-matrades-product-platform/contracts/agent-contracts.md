# Agent Contracts

**Contract family**: `matrades.agent.v1`
**Authority**: Agents advise; deterministic application services validate and mutate state.

## Invocation Envelope

Every logical-agent invocation accepts a versioned envelope:

| Field | Required | Meaning |
|---|---|---|
| `invocation_id` | yes | Idempotent execution identity |
| `workflow_id` / `workflow_version` | yes | Owning durable workflow state |
| `agent_id` | yes | One fixed logical role |
| `agent_contract_version` | yes | Input/output schema version |
| `configuration_version_id` | yes | Matrades-owned runtime configuration |
| `selected_runtime` | yes | `CODEX_APP_SERVER` by default or explicitly selected `LITELLM` |
| `runtime_selection_source` | yes | `PLATFORM_DEFAULT`, `AGENT_OVERRIDE`, or `MODEL_PROFILE` |
| `system_prompt_version_id` | yes | Resolved prompt version |
| `user_prompt_version_id` | yes | Independently resolved prompt version |
| `tool_permission_set_version_id` | yes | Immutable allowed-tool authority |
| `owner_id` / `account_id` | scoped | Authorization and data-isolation scope |
| `context_refs` | yes | Immutable structured snapshot/evidence references |
| `requested_at` / `deadline_at` | yes | UTC timing and timeout boundary |
| `correlation_id` / `causation_id` | yes | Audit chain |

Inputs contain structured facts and references, not raw secrets. Current price, equity, policy, risk,
strategy status, and broker state must already come from authoritative services.

## Result Envelope

Every result is schema validated before use:

```text
result_id
invocation_id
agent_id
contract_version
status: SUCCESS | DEGRADED | REASSESS | REJECT | FAILED
output: role-specific structured object
evidence_refs[]
source_times[]
assumptions[]
uncertainties[]
warnings[]
selected_runtime
actual_runtime
actual_model_id
actual_provider
fallback_used
tool_call_summaries[]
started_at
completed_at
```

Free-form prose may accompany a result for user explanation but never supplies canonical mutations,
position size, current state, or hard-policy outcomes. Malformed or unauthorized output is `FAILED`;
critical workflows block or degrade according to role policy.

## Fixed Registry

| Agent ID | Core responsibility | Typical inputs | Output boundary |
|---|---|---|---|
| `orchestrator` | Coordinate bounded agent steps | Workflow state and contracts | Next requested step; never a hard financial decision |
| `forex_research` | Rank Forex candidates | Normalized research snapshots | Ranked evidence and exclusions |
| `metals_research` | Rank metals candidates | Normalized research snapshots | Ranked evidence and exclusions |
| `crypto_research` | Rank crypto candidates | Coinbase/CoinGecko normalized context | Ranked evidence and exclusions |
| `technical_analyst` | Interpret technical evidence | Deterministic indicator/structure results | Structured interpretation |
| `fundamental_analyst` | Interpret macro/events/news | Structured macro/event evidence | Bias, conflicts, event risks |
| `sentiment_analyst` | Interpret positioning/sentiment | Structured observations | Bias, crowding, conflicts |
| `regime_analyst` | Interpret fingerprint dimensions | Structured analysis results | Regime label/quality evidence |
| `strategy_selector` | Rank eligible candidates | Pre-filtered validated strategies | Ranked suitability; no activation |
| `strategy_researcher` | Propose hypotheses | Research/knowledge context | Non-canonical hypothesis |
| `strategy_assistant` | Assist a user draft | Draft revision and permitted knowledge | Suggestions/change proposals only |
| `critic` | Adversarially challenge eligible setup | Policy/risk-passed candidate | PASS, REJECT, or REASSESS |
| `trade_monitor` | Interpret active-position evidence | Reconciled broker/market/policy state | HOLD or proposed management action |
| `journal` | Produce narrative summary | Immutable trade/journal facts | Non-authoritative commentary |
| `performance` | Interpret structured metrics | Calculated performance records | Findings/research triggers; no rule mutation |

Required definitions cannot be deleted. Registry evolution requires an approved constitution or
product-specification change.

## Runtime, Model, and Prompt Resolution

1. Resolve runtime independently: explicit LiteLLM assignment on the agent or its selected profile
   → otherwise `CODEX_APP_SERVER`. Runtime does not inherit from the Orchestrator.
2. Resolve the model within that runtime: agent custom model/profile → compatible Orchestrator
   model/profile in the same runtime → selected-runtime platform default.
3. Validate required capabilities and runtime equality before activation and before fallback use.
4. Resolve system prompt independently: agent system override → orchestrator system prompt →
   platform system default.
5. Resolve user prompt independently: agent user override → orchestrator user prompt → platform
   user default.
6. Resolve allowed tools from the immutable permission-set version; prompts, models, and runtimes cannot add or
   remove tools.
7. Persist selected and actual runtime, runtime selection source, configured and actual
   model/provider, same-runtime fallback reason, both prompt versions, tool set, retries, code
   release, input/evidence references, and structured result.

An override in one prompt type has no effect on the other. A configured or exhausted Codex runtime
MUST NOT fall back to LiteLLM unless a new explicit agent/profile configuration is activated. If no
compatible model exists in the selected runtime, the agent is unavailable; a critical workflow must
not continue as though the role passed.

## Tool Invocation Contract

Every tool call includes invocation/owner/account scope, tool/action, schema version, arguments,
idempotency key when mutating, and correlation ID. The runtime checks the permission-set version
before dispatch and records a redacted result summary.

Default prohibitions for all agents:

- no broker write;
- no prop-rule or guardrail activation/write;
- no direct credential read;
- no strategy activation or lifecycle bypass;
- no direct canonical draft mutation;
- no approval resolution on behalf of a user.

`strategy_assistant` may read a permitted draft/repository/knowledge/backtest summary and propose a
suggestion. Only the suggestion decision application service can accept/edit/reject and create an
immutable rule revision.

## Knowledge Boundary

Knowledge results include source/document/segment IDs, version/date, owner scope, retrieval score,
and retrieval audit ID. Agent results must distinguish retrieved context from user-authored rules and
structured facts. Risk and Policy engines are not agents and never consume semantic results.

## Critical Failure Policy

- Risk, policy, and effective-limit services unavailable: no actionable HIL-2.
- Required Critic unavailable or invalid: no actionable HIL-2.
- Codex runtime unavailable without explicit LiteLLM assignment: required role is unavailable and
  its workflow becomes DEGRADED or BLOCKED; no automatic cross-runtime retry occurs.
- Research specialist unavailable: research run becomes DEGRADED or fails according to required-role
  policy; no fabricated result.
- Strategy Assistant unavailable: draft editing continues manually; assistance is DEGRADED.
- Journal/performance narrative unavailable: structured trade and metric records continue.

## Contract Tests

- Validate all 15 IDs, required capabilities, and protected status.
- Verify every required agent resolves to `CODEX_APP_SERVER` when no explicit override exists.
- Verify LiteLLM runs only after an explicit agent/profile assignment and never by automatic fallback.
- Exercise every system/user prompt inheritance combination independently.
- Reject incompatible primary/fallback models and mixed-runtime fallback chains.
- Prove model/prompt changes leave tool permissions unchanged.
- Reject malformed, wrong-version, out-of-scope, or stale-context output.
- Prove no agent output can directly mutate policy, risk, broker, approval, or canonical strategy state.
- Record selected/actual runtime, runtime source, actual model/fallback/prompts/tools/code for
  successful and failed executions.
