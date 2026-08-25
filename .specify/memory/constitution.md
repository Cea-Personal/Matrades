<!--
Sync Impact Report
- Version change: 1.3.0 -> 2.0.0
- Modified principles: IV. Evidence-Based, Equally Validated Strategies now supports only
  AI_GENERATED and AI_ASSISTED strategy origins
- Added sections: none
- Removed sections: HUMAN_CREATED and IMPORTED strategy-origin obligations
- Source lineage: TraderX 1.0.0; Matrades 1.0.0, 1.1.0, 1.2.0, and 1.3.0
- Follow-up TODOs: none
-->
# Matrades Constitution

Matrades is an AI-assisted, multi-agent market-research, strategy-development,
risk-management, and trading decision-support platform for Forex, metals, and
cryptocurrency. It automates research, analysis, strategy discovery and assistance,
validation, opportunity detection, risk assessment, monitoring, journaling, knowledge
retrieval, and performance analysis while preserving human control of live trading.

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative. MUST and MUST NOT
define non-negotiable requirements. A deviation from SHOULD or SHOULD NOT requires an
explicit rationale in the governing specification or plan.

## Core Principles

### I. Ordered Authority and Deterministic Safety

Every trading decision MUST enforce this authority order:

1. broker and prop-firm hard rules;
2. internal risk limits and guardrails;
3. validated strategy rules;
4. authoritative structured market and account data;
5. current market evidence;
6. AI reasoning;
7. human approval.

A lower authority MUST NOT override a higher authority. Human approval, AI output,
retrieved knowledge, prompts, and strategy authorship MUST NOT bypass a hard block.
Policy, permissions, financial calculations, and critical safety controls MUST be
implemented deterministically wherever their inputs and rules can be structured. An
LLM MUST NOT be the final enforcement mechanism for position sizing, drawdown, account
eligibility, policy, or risk. This ordering makes safety behavior predictable and
prevents persuasive model output from superseding enforceable facts.

### II. Human Control and Manual Live Execution

Matrades MUST implement three explicit human-in-the-loop gates:

- HIL-1 controls the active market universe. The normal recommendation is one Forex,
  one metal, and one cryptocurrency instrument; the user can APPROVE, REPLACE, or
  RERUN RESEARCH.
- HIL-2 controls acceptance of a trade idea. The user can TAKE, WAIT, or REJECT only
  after analysis, strategy eligibility, policy, equity, guardrail, portfolio-risk, and
  critic checks pass.
- HIL-3 controls discretionary changes to a live position. Moving Stop Loss, changing
  Take Profit, reducing exposure, taking partial profit, or exiting early requires the
  user to APPROVE, WAIT, or REJECT.

TAKE approves an idea; it MUST NOT execute a trade. Live execution MUST remain manual
by default. After TAKE, the system MUST wait for manual entry and broker reconciliation.
Broker-side Stop Loss and Take Profit instructions MAY execute without another human
decision. Autonomous live execution, removal of a human gate, or weakening of manual
control requires an explicit constitutional amendment.

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
account state, equity, positions, orders, Stop Loss and Take Profit, drawdown, policy,
guardrails, strategy status, risk, and performance metrics. Sources MUST retain
provenance and freshness metadata. Stale, contradictory, missing, or unhealthy critical
data MUST be surfaced and MUST block dependent trading actions when safety cannot be
established.

Retrieval-augmented generation MAY provide context from source documents, research,
journals, and historical notes. Retrieved text MUST NOT calculate final risk, establish
current account state, activate a strategy or policy, authorize a trade, or bypass a
hard block. Where retrieved context conflicts with an authoritative structured source,
the structured source governs. This boundary allows useful institutional memory without
mistaking plausible text for current operational truth.

### VI. Safe Failure and the Valid No-Trade Outcome

When critical evidence is unavailable, stale, contradictory, or uncertain, Matrades
MUST prefer WAIT, NO TRADE, BLOCK, or DEGRADED over forced action. NO TRADE is a valid
and successful outcome. The platform MUST optimize for decision quality, compliance,
capital preservation, evidence, and robustness—not signal volume, trade count, or
unnecessary strategy generation.

Hard blocks and circuit breakers MUST cover applicable drawdown breaches, insufficient
risk capacity, stale market or broker state, unavailable policy or risk engines,
critical agent failure, and broker or bridge disconnection. Existing positions SHOULD
continue to be monitored when this can be done safely. The system MUST NOT fabricate
certainty, silently downgrade a hard failure, or convert an unknown state into approval.

### VII. Orchestrated Agents and Provider Independence

Matrades MUST use stable logical agent roles coordinated by an Orchestrator. The
Orchestrator owns workflows, dependencies, state transitions, retries, failures, and
human gates; specialist roles own bounded research or analysis responsibilities. Agents
MUST communicate through versioned structured outputs, declare evidence and uncertainty,
and operate only with explicitly allowed tools. No agent may bypass deterministic policy
or risk services.

Agent identity MUST be independent of runtime model selection. Each configurable agent
MUST support provider, model, credential reference, parameters, fallback models, and
independent INHERIT/OVERRIDE behavior for system and user prompts. Resolution MUST be
deterministic and auditable. LiteLLM MAY be the reference gateway, but business logic
MUST NOT depend on one model vendor, broker, exchange, market-data source, calendar
provider, or notification service.

### VIII. Secure, UI-First Configuration

Routine operational configuration MUST be available through the UI, including accounts,
prop-firm rules, guardrails, data and broker connections, agents, models, prompts,
credentials, notifications, and knowledge sources. Operations and configuration MUST
remain visibly separated. Fixed roles required by the orchestrator MUST be protected
from accidental deletion, and invalid critical configurations MUST NOT silently activate.

Authentication, verified email, multi-factor enrollment, and recovery codes MUST precede
account activation. Sign-in MUST require an MFA challenge, and sensitive configuration
changes MUST require step-up authentication. Authorization MUST enforce least privilege.
Secrets MUST be encrypted at rest and in transit, masked after entry, referenced rather
than embedded in prompts or logs, and inaccessible to agents without an explicit need.

### IX. Adapter Boundaries and Broker Reconciliation

Broker, exchange, market-data, calendar, model, and notification integrations MUST use
replaceable adapters or registries. Core agents and business rules MUST depend on common
contracts rather than provider-specific APIs. Broker connections MUST default to
read-only. Matrades MUST support a health-reporting MT5 Bridge, including MT5 under Wine
on macOS, without making MT5 a permanent architectural dependency.

Approval MUST NOT imply execution. Following HIL-2 TAKE, a proposal enters an
awaiting-manual-entry state. Once a broker or bridge detects a position, Matrades MUST
reconcile it to an approved setup. The reconciled broker values—including actual entry,
size, protections, fees, and P&L—become authoritative for live monitoring. Disconnected
or stale broker state MUST be marked clearly and MUST NOT be represented as confirmed.

### X. Auditability, Reproducibility, and Controlled Learning

Material recommendations and state changes MUST be reconstructable from the data,
strategy and version, policy and guardrails, account state, agent configuration, actual
model and provider, prompt versions, tools used, human decisions, broker outcome, code
version, and timestamps. User-facing explanations MUST state why an action is proposed,
its evidence, risk, restrictions, and invalidation without exposing hidden chain-of-thought.

Critical deterministic components MUST have automated boundary, unit, integration, and
contract tests as applicable. Backtests and material recommendations SHOULD be
reproducible whenever source data permits. Live strategies MUST NOT silently self-modify.
Learning follows an explicit lifecycle: observation or human idea, research, formal
specification, similarity review, deterministic implementation, validation, paper
trading, and controlled promotion. Recent performance may trigger investigation or
suspension, never uncontrolled live rule changes.

## Product and Operational Constraints

- Matrades' initial market scope is Forex, metals, and cryptocurrency. Instruments MUST
  be configurable and MUST NOT be permanently hard-coded.
- A HIL-2 proposal MUST include instrument, direction, entry or entry zone, Stop Loss,
  Take Profit targets, size, risk percentage, maximum expected loss, Risk:Reward,
  strategy identity and version, regime, evidence, invalidation, current equity,
  remaining loss and portfolio capacity, and policy, guardrail, risk, and critic status.
- The deterministic Risk Engine owns authoritative position size and aggregate exposure
  calculations. The Critic MUST adversarially review otherwise eligible proposals before
  HIL-2 but MUST NOT override hard blocks.
- Reconciled positions MUST be monitored for price, structure, liquidity, volatility,
  momentum, fundamentals, events, invalidation, policy, P&L, and remaining risk as
  applicable. Position-changing recommendations route through HIL-3.
- A journal MUST retain proposed and actual trades, approvals, strategy and policy
  versions, relevant evidence, management recommendations, outcomes, fees, MAE, MFE,
  model and prompt identities, and timestamps. Performance MUST be attributable by
  instrument, strategy version, regime, session, and account where data permits.
- The UI MUST expose operational state using unambiguous statuses such as RESEARCHING,
  WAITING, ACTION REQUIRED, ACTIVE, BLOCKED, DEGRADED, and OFFLINE. A user MUST NOT need
  raw agent logs to know whether action is required.
- Integrations MUST expose health, last success, freshness, latency, and error state where
  practical. Observability MUST include workflow and agent status, actual provider and
  model, retries and fallbacks, tool invocation, and policy or validation failures while
  excluding secrets and hidden model reasoning.
- Notifications MAY use in-app, browser push, email, Telegram, or future adapters. Urgent
  approval, safety, and disconnection events SHOULD be distinguishable from informational
  messages.

## Development Workflow and Quality Gates

Every specification, plan, task set, implementation, and review MUST demonstrate
constitutional compliance. The following gates are mandatory:

1. **Specification gate**: identify affected human gates, authority layers, data sources,
   policy, risk, security, and failure states; define measurable acceptance criteria.
2. **Architecture gate**: preserve provider-neutral contracts, structured agent schemas,
   deterministic safety boundaries, least-privilege tool access, and secret isolation.
3. **Strategy gate**: preserve provenance and authorship, detect duplicates, separate
   specification from implementation, and apply the same validation lifecycle to every
   origin.
4. **Trading gate**: verify authoritative data freshness, exact account ruleset, equity,
   reserved and correlated risk, strategy eligibility, critic review, and the relevant
   human approval before an actionable recommendation.
5. **Testing gate**: test position sizing, drawdown and portfolio calculations, policy and
   guardrail boundaries, circuit breakers, strategy rules and deduplication, data
   normalization, broker reconciliation, prompt/model resolution, credentials, and
   authorization. Safety-critical defects block release.
6. **Review gate**: reviewers MUST reject changes that weaken a hard block, human gate,
   audit trail, authentication control, or validation requirement without an approved
   constitutional amendment and migration plan.
7. **Release gate**: schema, policy, strategy, prompt, and configuration changes MUST be
   versioned where they affect reproducibility. Rollback or safe-disable behavior MUST be
   defined for critical integrations and workflows.

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
for clarifications that do not change obligations. Autonomous live execution, removal of
a mandatory HIL gate, override of a hard risk or prop-firm rule, weaker credential
isolation, removal of authentication or MFA, or reduced live-strategy validation MUST
receive explicit constitutional consideration and cannot be introduced only through an
implementation specification.

Compliance MUST be reviewed during specification, planning, code review, and before
release. Any exception MUST be documented with scope, owner, expiry, risk analysis, and
remediation plan; no exception may permit live trading that violates a hard external
rule. The constitution itself MUST be reviewed whenever product authority, execution
mode, account model, or safety boundary changes.

**Version**: 2.0.0 | **Ratified**: 2026-08-22 | **Last Amended**: 2026-08-25
