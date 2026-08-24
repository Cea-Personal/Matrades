# Quickstart Validation Guide: Matrades Product Platform

This guide defines the runnable V1 validation interface to be implemented by the task phase. It
proves the constitutional paths end to end without containing application implementation. References:
[data model](./data-model.md), [OpenAPI](./contracts/openapi.yaml),
[events](./contracts/events.md), [agents](./contracts/agent-contracts.md), and
[adapters](./contracts/adapter-contracts.md).

## Prerequisites

- Docker with Compose support
- Python 3.13 and `uv`
- Node.js 24 LTS with npm
- Test/sandbox credentials for configured providers; no live broker write permission
- MT5 demo account and bridge only for broker validation scenarios

Copy the future `.env.example` to a local ignored environment file. Use test credentials and a
development vault key; never commit secrets.

## Start the Planned Development Environment

```bash
docker compose -f infra/compose/dev.yml up --build -d postgres redis api worker agent-worker web
uv sync --all-packages --dev
npm install
uv run alembic -c infra/migrations/alembic.ini upgrade head
```

Start LiteLLM only when validating the explicit alternative-runtime path:

```bash
docker compose -f infra/compose/dev.yml --profile litellm up --build -d litellm
```

Expected result:

- API, background worker, Codex agent worker, web, PostgreSQL, and Redis health checks are healthy;
  LiteLLM is absent unless its optional profile was explicitly started.
- TimescaleDB and pgvector extension checks pass or the configured compatible adapter reports why
  an external substitute is active.
- Required agent seed validation reports exactly 15 protected logical IDs, including
  `strategy_assistant`.
- No provider or broker credential value appears in command output.

## Validate Contracts and Architecture

```bash
uv run pytest tests/contract tests/security/test_architecture_boundaries.py
npm run test:contracts --workspace apps/web
```

Expected result:

- OpenAPI, event, adapter, and agent schemas validate.
- Domain dependency tests reject agent/provider access to broker writes, policy writes, guardrail
  writes, raw credentials, or canonical strategy mutation.
- System and user prompt inheritance are independent.
- PostgreSQL is the durable owner of workflow, approval, reservation, and audit state.

## Scenario 1: Secure Account Configuration

1. Create a user, verify email, enroll TOTP MFA, capture recovery codes once, and sign in with MFA.
2. Add a masked provider credential and a read-only broker/MT5 connection.
3. Create a prop-firm program/ruleset draft, verify it, activate its version, and create a stricter
   internal guardrail profile.
4. Attempt a sensitive credential/risk change without step-up, then repeat after step-up.

```bash
uv run pytest tests/e2e/test_secure_configuration.py -q
```

Expected result:

- Activation and sign-in cannot bypass MFA.
- The first sensitive mutation is denied; the step-up-authorized mutation succeeds and is audited.
- Reloaded credential data is masked, and scans find no raw secret in logs or prompts.
- Effective limits show every contributor and select the strictest value.

## Scenario 2: Equity and Dynamic Risk Capacity

Load deterministic fixtures for a nominal 200,000 account whose current equity, daily loss,
reserved Stop Loss risk, and correlated exposure vary by case.

```bash
uv run pytest tests/property/risk tests/e2e/test_equity_capacity.py -q
```

Required cases:

- current equity supports PASS;
- original balance appears sufficient but current equity causes HARD_BLOCK;
- requested size causes REDUCE_SIZE and broker-increment rounding down;
- no/malformed Stop Loss produces unbounded-risk HARD_BLOCK;
- unrealized profit is excluded unless the active ruleset permits it;
- EURUSD BUY plus GBPUSD BUY exceeds the shared USD/correlation cap;
- a static trade slot remains but portfolio capacity is zero;
- two concurrent proposals cannot reserve the same remaining capacity;
- stale/wrong-account snapshots and stale FX rates block.

Expected result: every result contains the complete pre-trade equity snapshot, limiting sources,
projected post-trade state, and candidate-specific additional capacity. Tightening a limit or adding
exposure never increases permitted size.

## Scenario 3: Agent and Prompt Resolution

Leave the Orchestrator and `technical_analyst` on their default Codex runtime. Configure Model A and
both Orchestrator prompts; configure `technical_analyst` with Codex Model B, a system-prompt override,
user-prompt inheritance, and a compatible Codex fallback. Make Model B fail. Then explicitly assign
a LiteLLM-backed profile to `sentiment_analyst` and repeat its test run.

```bash
uv run pytest tests/integration/agents tests/e2e/test_agent_configuration.py -q
```

Expected result:

- All 15 required agents resolve to `CODEX_APP_SERVER` before an explicit alternative is assigned.
- The first technical-analysis run resolves agent system prompt + orchestrator user prompt.
- A later run uses the compatible Codex fallback and records selected/actual runtime, configured/
  actual models, and the reason.
- Only `sentiment_analyst` uses LiteLLM after its explicit profile assignment; connecting LiteLLM
  does not reassign any other agent.
- Exhausting Codex fallbacks produces DEGRADED or BLOCKED and never retries through LiteLLM.
- Tool permissions remain byte-for-byte the same across model/prompt changes.
- An incompatible required agent configuration cannot activate.

## Scenario 4: Daily Research and HIL-1

Use recorded Twelve Data, Coinbase, CoinGecko, macro, positioning, and calendar fixtures.

```bash
uv run pytest tests/replay/research tests/e2e/test_hil1_market_selection.py -q
```

Expected result:

- One Forex, metal, and crypto candidate is ranked from normalized evidence within the SC-012 target.
- REPLACE changes only the chosen category and creates a new selection version.
- RERUN RESEARCH creates a new run rather than overwriting prior evidence.
- Stale Coinbase data blocks affected crypto action; stale knowledge only degrades contextual research.

## Scenario 5: Strategy Lab to Promotion

Create one partial AI-assisted XAUUSD idea, reject one suggestion, edit another, complete required
rules, and submit it. Repeat with AI-generated, manual, and imported origins.

```bash
uv run pytest tests/e2e/test_strategy_origins.py tests/replay/strategy_validation -q
```

Expected result:

- Conversation never changes canonical rules; accepted/edit revisions retain provenance.
- An exact cross-origin duplicate is blocked from creating a new identity.
- An active strategy improvement creates a new draft and leaves the active version immutable.
- All origins use the same compiler, point-in-time backtest, out-of-sample, walk-forward, stress/
  Monte Carlo, account-policy simulation, paper, and promotion stages.
- Backtest, paper, and live fixture evaluation produce equivalent signals for the same artifact.

## Scenario 6: HIL-2, Manual Entry, and Reconciliation

Seed one validated strategy and a current account/market snapshot. Produce one PASS, one reduced-size,
and one hard-blocked candidate.

```bash
uv run pytest tests/e2e/test_hil2_manual_reconciliation.py -q
```

Expected result:

- HARD_BLOCK never enters the actionable approval queue.
- PASS/REDUCE_SIZE proposals contain all FR-032 and FR-084 fields and complete within SC-013.
- WAIT/REJECT release candidate risk. TAKE preserves the reservation and enters
  `AWAITING_MANUAL_ENTRY` without a broker write.
- A unique broker position auto-reconciles; an ambiguous one requests user confirmation.
- Actual broker entry, size, protections, fees, and P&L supersede proposed values.

## Scenario 7: Monitoring and HIL-3

```bash
uv run pytest tests/e2e/test_hil3_trade_management.py -q
```

Expected result:

- HOLD creates no approval.
- A validated partial-profit or Stop Loss recommendation creates HIL-3.
- APPROVE records intent only; the user performs the broker change manually and reconciliation records it.
- A broker-side Stop Loss/Take Profit execution closes the trade without HIL-3.
- Bridge disconnect marks state stale, blocks dependent actions, and does not fabricate confirmation.

## Scenario 8: Knowledge Isolation and Failure

```bash
uv run pytest tests/integration/knowledge tests/security/test_knowledge_isolation.py \
  tests/failure/test_knowledge_outage.py -q
```

Expected result:

- Cross-owner/account search returns no data, including through semantic-nearest candidates.
- Results retain source/document/segment/version provenance and retrieval audit.
- Retrieved prop text produces only a draft rule until user verification/versioned activation.
- Adversarial retrieved text cannot change equity, policy, risk, approval, strategy activation, or tools.
- Vector/embedding failure degrades contextual work while structured safety continues or safely blocks.

## Scenario 9: Full Release Gate

```bash
uv run pytest tests/unit tests/property tests/integration tests/contract tests/replay \
  tests/security tests/failure -q
npm test --workspaces
npm run test:e2e --workspace apps/web
```

Expected result:

- SC-001 through SC-015 publish machine-readable evidence and all pass.
- The full journal reconstructs sampled decisions from input snapshots, policy/risk/strategy/config/
  prompt/code versions, human actions, and broker events.
- Duplicate/out-of-order provider, task, approval, and broker events are idempotent.
- Backup restore meets the planned 15-minute RPO/four-hour RTO exercise.
- There is no route, tool, or adapter operation capable of autonomous V1 broker entry/modification/exit.

## Stop Conditions

Do not proceed to live-connected validation if any of these occurs:

- risk/policy/critic unavailable or a hard-block candidate reaches HIL-2;
- current account, market, calendar, or broker data violates its required freshness policy;
- raw secrets appear in UI responses, logs, prompts, events, fixtures, or reports;
- any required agent defaults to LiteLLM, or any execution changes runtime without an explicitly
  activated per-agent or model-profile selection;
- any agent can mutate canonical strategy, policy, guardrail, approval, or broker state directly;
- TAKE or HIL-3 APPROVE sends a broker write;
- strategy validation stages can be skipped or active rules mutate in place;
- a cross-user/account authorization or retrieval-isolation test fails.
