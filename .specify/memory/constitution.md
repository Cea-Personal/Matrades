<!--
Sync Impact Report
- Version change: 2.1.0 -> 3.0.0
- Modified principles: I. Ordered Authority and Deterministic Safety removes routine human
  approval from the execution authority chain and adds execution permissions and kill switches;
  II. Human Control and Manual Live Execution -> Autonomous Execution and Human Safety Control;
  V. Authoritative Data and Bounded Knowledge Retrieval adds read-only grounded Q&A and live
  journal indexing boundaries; VI. Safe Failure and the Valid No-Trade Outcome adds execution
  uncertainty and kill-switch behavior; VII. Orchestrated Agents and Provider Independence
  replaces human-gate orchestration with autonomous lifecycle orchestration and isolates broker
  writes behind deterministic execution; VIII. Secure, UI-First Configuration adds execution
  permissions and kill switches; IX. Adapter Boundaries and Broker Reconciliation adds bounded,
  idempotent full-lifecycle broker execution; X. Auditability, Reproducibility, and Controlled
  Learning expands execution and live-journal audit requirements
- Added sections: none
- Removed sections: mandatory HIL-1, HIL-2, and HIL-3 workflow requirements and manual-live-
  execution governance
- Source lineage: TraderX 1.0.0; Matrades 1.0.0, 1.1.0, 1.2.0, and 1.3.0
- Follow-up TODOs: none
-->
# Matrades Constitution

Matrades is an AI-assisted, multi-agent market-research, strategy-development,
risk-management, and autonomous trading platform for Forex, metals, cryptocurrency, and
stocks across spot, CFD, and futures instruments. It automates research, analysis, strategy
discovery and assistance, validation, opportunity detection, risk assessment, full-lifecycle
trade execution and management, monitoring, live journaling, knowledge retrieval,
notifications, and performance analysis while preserving deterministic safety and immediate
human stop authority.

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative. MUST and MUST NOT
define non-negotiable requirements. A deviation from SHOULD or SHOULD NOT requires an
explicit rationale in the governing specification or plan.

## Core Principles

### I. Ordered Authority and Deterministic Safety

Every trading decision MUST enforce this authority order:

1. emergency kill switches and applicable legal, broker, exchange, and prop-firm hard rules;
2. internal risk limits and guardrails;
3. explicit per-account execution permissions;
4. validated strategy rules;
5. authoritative structured market, instrument, order, position, and account data;
6. current market evidence;
7. bounded AI reasoning.

A lower authority MUST NOT override a higher authority. Automation configuration, AI output,
retrieved knowledge, prompts, strategy authorship, and manual intervention through Matrades
MUST NOT bypass a hard block or active kill switch.
Policy, permissions, financial calculations, and critical safety controls MUST be
implemented deterministically wherever their inputs and rules can be structured. An
LLM MUST NOT be the final enforcement mechanism for position sizing, drawdown, account
eligibility, policy, risk, broker-write authorization, idempotency, or reconciliation.
This ordering makes autonomous behavior predictable and prevents persuasive model output
from superseding enforceable facts.

### II. Autonomous Execution and Human Safety Control

Matrades MUST NOT require HIL-1, HIL-2, or HIL-3 approval gates for routine market
selection, trade entry, order cancellation, Stop Loss or Take Profit creation or change,
partial close, exposure reduction, early exit, or full exit. Eligible research candidates
MUST continue through the configured analysis pipeline, and a validated Trade Plan MUST
execute automatically when the applicable account permission is enabled and every
deterministic policy, risk, data-freshness, strategy, critic, permission, and safety check
passes.

Broker connectivity MUST begin read-only. Full-lifecycle broker writes MAY be enabled only
through explicit, independently configurable per-account permissions for entry, cancellation,
protection changes, partial closes, and full exits. A disabled permission MUST hard-block that
action. Every account and the platform as a whole MUST expose a durable emergency kill switch
that immediately blocks new entries and discretionary broker writes without removing broker-
hosted protective orders. Kill-switch activation MUST NOT depend on an AI agent.

Human control is exercised through strategy canonicalization, risk and policy configuration,
execution permissions, visibility, safe-disable controls, and emergency stop authority—not
through routine trade approvals. Manual broker-side activity MAY occur outside Matrades, but
Matrades MUST reconcile it as external authoritative state and MUST NOT misrepresent it as an
autonomous action. This model enables full automation without surrendering deterministic
constraints or immediate human stop authority.

### III. Account-Aware Risk and Prop-Firm Compliance

Every live trade eligibility decision MUST use current account state, including balance,
equity, floating and realized P&L, daily and total drawdown, open positions, remaining
Stop Loss risk, available loss capacity, portfolio exposure, and correlated exposure.
Original account size alone MUST NOT establish eligibility. Additional trade capacity
MUST be calculated dynamically; a configured concurrent-trade count is a ceiling, not
an entitlement. Floating profit MUST NOT be treated as available risk unless the active
policy explicitly permits it.

Prop-firm policy MUST be scoped by firm, program, account type, account size where
applicable, ruleset version, and trading account. Rulesets MUST record their source,
effective date, verification state, last verification date, and version. Historical
decisions MUST retain the ruleset used at the time. Imported or AI-extracted rules MUST
be reviewed, edited where needed, verified, and explicitly activated before becoming
authoritative. Internal guardrails operate independently; the strictest applicable
external or internal limit MUST govern.

For spot, CFD, and futures instruments, the Risk Engine MUST use authoritative instrument
metadata such as contract size, tick or point value, margin, financing or funding, expiry or
roll terms, venue, and currency conversion when applicable. Missing or stale contract metadata
MUST prevent autonomous execution when worst-case risk cannot be established.

### IV. Evidence-Based, Equally Validated Strategies

Matrades MUST support exactly `AI_GENERATED` and `AI_ASSISTED` strategy origins and
persist origin, authorship, accepted AI suggestions, lineage, and version history.
`AI_GENERATED` begins from autonomous Strategy Researcher output. `AI_ASSISTED` begins
from a human description that AI expands into a complete, step-by-step proposed strategy.
In both cases, AI MUST NOT silently alter canonical strategy rules; a human MUST approve
the proposed specification before it becomes canonical. Origin MUST NOT grant
preferential selection, automatic activation, or reduced scrutiny.

Before live eligibility, every strategy MUST have a complete, deterministic
specification; pass canonicalization and duplicate/variant/version classification; be
implemented separately from its prose or AI generation step; and complete the required
validation lifecycle. At minimum, validation MUST cover historical backtesting,
out-of-sample testing, walk-forward analysis, applicable stress or Monte Carlo testing,
prop-firm simulation, and paper trading. Material rule changes MUST create a new version.
Instrument parameter profiles MAY share one strategy identity when the underlying rules
are unchanged. Selection MUST be evidence-based and limited to validated strategies
compatible with the current instrument, regime, account policy, and strategy health.

### V. Authoritative Data and Bounded Knowledge Retrieval

Structured systems MUST remain authoritative for prices, candles, market timestamps,
asset class, instrument type, contract or venue terms, account state, equity, positions,
orders, Stop Loss and Take Profit, drawdown, policy, guardrails, strategy status, risk,
and performance metrics. Sources MUST retain provenance and freshness metadata. Stale,
contradictory, missing, or unhealthy critical data MUST be surfaced and MUST block dependent
trading actions when safety cannot be established.

Retrieval-augmented generation MAY provide context from source documents, research,
journals, live monitoring observations, post-trade summaries, and historical notes. Live
journal events MAY be indexed continuously, but the immutable structured journal remains
authoritative. A knowledge-facing agent MUST be read-only, cite authorized evidence, label
inference and insufficiency, and have no Trade Plan, execution-service, or broker-write tool.
Retrieved text MUST NOT calculate final risk, establish current account state, activate a
strategy or policy, authorize or execute a trade, or bypass a hard block. Where retrieved
context conflicts with an authoritative structured source, the structured source governs.
This boundary allows useful institutional memory without mistaking plausible or historical
text for current operational truth.

### VI. Safe Failure and the Valid No-Trade Outcome

When critical evidence is unavailable, stale, contradictory, or uncertain, Matrades
MUST prefer WAIT, NO TRADE, BLOCK, or DEGRADED over forced action. NO TRADE is a valid
and successful outcome. The platform MUST optimize for decision quality, compliance,
capital preservation, evidence, and robustness—not signal volume, trade count, or
unnecessary strategy generation.

Hard blocks and circuit breakers MUST cover applicable drawdown breaches, insufficient
risk capacity, stale market or broker state, unavailable policy or risk engines,
critical agent failure, active kill switches, disabled execution permissions, broker or
bridge disconnection, and uncertain execution outcomes. Existing positions SHOULD continue
to be monitored when this can be done safely. A timed-out or ambiguous broker response MUST
be reconciled before retry and MUST NOT be assumed to have failed. The system MUST NOT
fabricate certainty, silently downgrade a hard failure, or convert an unknown state into
execution authorization.

### VII. Orchestrated Agents and Provider Independence

Matrades MUST use stable logical agent roles coordinated by an Orchestrator. The
Orchestrator owns workflows, dependencies, state transitions, retries, failures, and
autonomous lifecycle progression; specialist roles own bounded research, analysis,
monitoring, journaling, or explanation responsibilities. Agents MUST communicate through
versioned structured outputs, declare evidence and uncertainty, and operate only with
explicitly allowed tools. No agent may bypass deterministic policy, risk, permission,
kill-switch, or execution services. Agents MUST NOT receive raw broker-write credentials;
all broker writes MUST pass through a deterministic execution boundary.

Agent identity MUST be independent of runtime model selection. Each configurable agent
MUST support provider, model, credential reference, parameters, fallback models, and
independent INHERIT/OVERRIDE behavior for system and user prompts. Resolution MUST be
deterministic and auditable. LiteLLM MAY be the reference gateway, but business logic
MUST NOT depend on one model vendor, broker, exchange, market-data source, calendar
provider, or notification service.

### VIII. Secure, UI-First Configuration

Routine operational configuration MUST be available through the UI, including accounts,
prop-firm rules, guardrails, data and broker connections, agents, models, prompts,
credentials, notifications, knowledge sources, per-account execution permissions, and
account and platform kill switches. Operations and configuration MUST remain visibly
separated. Active automation state and kill-switch state MUST remain visible from operational
views. Fixed roles required by the orchestrator MUST be protected from accidental deletion,
and invalid critical configurations MUST NOT silently activate.

Authentication, verified email, multi-factor enrollment, and recovery codes MUST precede
account activation. Sign-in MUST require an MFA challenge, and sensitive configuration
changes MUST require step-up authentication. Authorization MUST enforce least privilege.
Secrets MUST be encrypted at rest and in transit, masked after entry, referenced rather
than embedded in prompts or logs, and inaccessible to agents without an explicit need.

### IX. Adapter Boundaries and Broker Reconciliation

Broker, exchange, market-data, calendar, model, and notification integrations MUST use
replaceable adapters or registries. Core agents and business rules MUST depend on common
contracts rather than provider-specific APIs. Broker connections MUST default to read-only
until explicit account permissions enable bounded writes. Matrades MUST support a health-
reporting MT5 Bridge, including MT5 under Wine on macOS, without making MT5 a permanent
architectural dependency. Instrument adapters MUST distinguish spot ownership, CFD derivative
exposure, and futures contract exposure and MUST publish the contract and venue metadata
required by deterministic risk, execution, and reconciliation.

Every broker write MUST originate from a versioned Trade Plan or authorized autonomous
management action, pass current deterministic checks, carry an idempotency key or equivalent
command identity, and record its account permission state. Order entry, cancellation,
protection changes, partial closes, and full exits MUST be reconciled against broker state.
An uncertain response MUST be reconciled before retry. Actual broker values—including order
status, entry, fill quantity, size, protections, fees, and P&L—become authoritative for live
monitoring and journaling. Disconnected, stale, mismatched, or ambiguous broker state MUST be
marked clearly and MUST NOT be represented as confirmed or safe to modify.

### X. Auditability, Reproducibility, and Controlled Learning

Material recommendations, autonomous decisions, broker commands, and state changes MUST be
reconstructable from the data, strategy and version, Trade Plan, policy and guardrails,
account state, execution permissions and kill-switch state, agent configuration, actual model
and provider, prompt versions, tools used, configuration or emergency human actions, broker
outcome, code version, and timestamps. User-facing explanations MUST state why an action was
proposed, executed, blocked, changed, or exited; its evidence, risk, restrictions, and
invalidation; and the resulting broker state without exposing hidden chain-of-thought.

Critical deterministic components MUST have automated boundary, unit, integration, and
contract tests as applicable. Backtests and material recommendations SHOULD be
reproducible whenever source data permits. Live strategies MUST NOT silently self-modify.
Learning follows an explicit lifecycle: observation or human idea, research, formal
specification, similarity review, deterministic implementation, validation, paper
trading, and controlled promotion. Recent performance may trigger investigation or
suspension, never uncontrolled live rule changes.

The Journal agent MUST append immutable observations throughout every reconciled live trade
and MUST produce a consolidated post-trade summary. Continuous semantic indexing MAY lag or
fail without weakening the authoritative structured journal. Performance calculations MUST
separate backtest, paper-trading, and live evidence; headline metrics and stated edge MUST NOT
blend those populations. Confirmed trade entries MUST emit deduplicated notifications through
enabled channels, while unconfirmed submissions MUST NOT be described as entered trades.

## Product and Operational Constraints

- Matrades' initial market scope is Forex, metals, cryptocurrency, and stocks across spot, CFD,
  and futures instruments. Instruments and their provider mappings MUST be configurable and MUST
  NOT be permanently hard-coded.
- Each daily research cycle MUST produce one ranked candidate for every supported asset-class and
  instrument-type combination. The initial matrix is Forex, metals, cryptocurrency, and stocks
  crossed with spot, CFD, and futures. A combination without authoritative configured data MUST
  be marked DEGRADED or NOT CONFIGURED and MUST NOT reach autonomous trade construction.
- Instrument type MUST be explicit and semantically distinct: spot represents cash or underlying
  ownership, CFD represents derivative exposure, and futures represent contract exposure.
- An executable Trade Plan MUST include instrument, direction, entry or entry zone, Stop Loss,
  Take Profit targets, size, risk percentage, maximum expected loss, Risk:Reward, strategy
  identity and version, regime, evidence, invalidation, current equity, remaining loss and
  portfolio capacity, account execution permissions, and policy, guardrail, risk, and critic status.
- The deterministic Risk Engine owns authoritative position size and aggregate exposure
  calculations. The Critic MUST adversarially review otherwise eligible proposals before
  execution but MUST NOT override hard blocks or authorize broker writes.
- Reconciled positions MUST be monitored for price, structure, liquidity, volatility,
  momentum, fundamentals, events, invalidation, policy, P&L, and remaining risk as
  applicable. Position-changing actions MUST re-check permissions, policy, risk, current
  broker state, and kill switches before execution.
- A journal MUST retain Trade Plans, autonomous decisions, execution commands and results,
  actual trades, strategy and policy versions, relevant evidence, management actions,
  outcomes, fees, MAE, MFE, model and prompt identities, and timestamps. Performance MUST
  be attributable by evidence class, instrument, strategy version, regime, session, and
  account where data permits.
- Every active trade MUST expose its current Trade Plan beside an interactive chart with
  authoritative freshness and instrument-mapping state. The chart MAY show indicators,
  executions, protections, journal events, and management overlays but MUST NOT create a
  Trade Plan, execution-service request, or broker command.
- The UI MUST expose operational state using unambiguous statuses such as RESEARCHING,
  WAITING, EXECUTING, ACTIVE, BLOCKED, DEGRADED, KILL SWITCH ACTIVE, and OFFLINE. A user
  MUST NOT need raw agent logs to know whether automation is active, blocked, or unsafe.
- Integrations MUST expose health, last success, freshness, latency, and error state where
  practical. Observability MUST include workflow and agent status, actual provider and
  model, retries and fallbacks, tool invocation, and policy or validation failures while
  excluding secrets and hidden model reasoning.
- Notifications MAY use in-app, browser push, email, Telegram, or future adapters. Confirmed
  trade entries, safety events, kill-switch changes, and disconnections SHOULD be
  distinguishable from informational messages. Notifications MUST NOT claim execution before
  broker confirmation.

## Development Workflow and Quality Gates

Every specification, plan, task set, implementation, and review MUST demonstrate
constitutional compliance. The following gates are mandatory:

1. **Specification gate**: identify affected automation permissions, authority layers, data
   sources, policy, risk, security, execution, reconciliation, and failure states; define
   measurable acceptance criteria.
2. **Architecture gate**: preserve provider-neutral contracts, structured agent schemas,
   deterministic safety and execution boundaries, idempotency, reconciliation, least-privilege
   tool access, kill-switch durability, and secret isolation.
3. **Strategy gate**: preserve provenance and authorship, detect duplicates, separate
   specification from implementation, and apply the same validation lifecycle to every
   origin.
4. **Trading gate**: verify authoritative data freshness, exact account ruleset, equity,
   reserved and correlated risk, strategy eligibility, critic review, current per-account
   permission, kill-switch state, and broker connectivity before every autonomous broker write.
5. **Testing gate**: test position sizing, drawdown and portfolio calculations, policy and
   guardrail boundaries, circuit breakers, strategy rules and deduplication, data
   normalization, execution permissions, kill switches, command idempotency, broker
   reconciliation, uncertain outcomes, prompt/model resolution, credentials, and
   authorization. Safety-critical defects block release.
6. **Review gate**: reviewers MUST reject changes that weaken a hard block, execution
   permission, kill switch, deterministic broker-write boundary, audit trail, authentication
   control, or validation requirement without an approved constitutional amendment and
   migration plan.
7. **Release gate**: schema, policy, strategy, prompt, and configuration changes MUST be
   versioned where they affect reproducibility. Rollback or safe-disable behavior MUST be
   defined for critical integrations and workflows. Autonomous execution MUST remain disabled
   for an account until its permissions, broker capabilities, safeguards, and recovery paths
   pass release validation.

Complexity beyond these requirements MUST be justified by a concrete safety, compliance,
extensibility, or product need. Simpler designs that preserve all constitutional
guarantees are preferred.

## Governance

This constitution is the highest project authority. Specifications, plans, tasks,
implementation, prompts, agents, UI behavior, and operating procedures MUST comply with
it. A conflict is resolved in favor of this constitution. Implementation details MAY
change without amendment only when every constitutional guarantee remains intact.

An amendment MUST:

1. identify each affected principle and the motivation for change;
2. describe safety, financial, security, data, and migration consequences;
3. update the Sync Impact Report, version, and amendment date;
4. preserve the prior version in version control; and
5. be explicitly approved before dependent work is merged.

Versions follow semantic versioning: MAJOR for removal or incompatible redefinition of a
principle or governance guarantee; MINOR for a new principle or material expansion; PATCH
for clarifications that do not change obligations. Any change to autonomous execution scope,
per-account permission enforcement, kill-switch semantics, deterministic broker-write
authorization, hard risk or prop-firm rules, credential isolation, authentication or MFA, or
live-strategy validation MUST receive explicit constitutional consideration and cannot be
introduced only through an implementation specification.

Compliance MUST be reviewed during specification, planning, code review, and before
release. Any exception MUST be documented with scope, owner, expiry, risk analysis, and
remediation plan; no exception may permit live trading that violates a hard external
rule. The constitution itself MUST be reviewed whenever product authority, execution
mode, account model, or safety boundary changes.

**Version**: 3.0.0 | **Ratified**: 2026-08-22 | **Last Amended**: 2026-08-25
