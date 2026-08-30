# Event Contracts

**Contract family**: `matrades.event.v1`

Events are immutable facts emitted after the owning database transaction commits. They support UI
updates, workers, integrations, notifications and audit projections; they do not replace aggregate
state or grant authority.

## Event Envelope

```text
event_id
event_type
schema_version
occurred_at
recorded_at
owner_id
account_id?
aggregate_type
aggregate_id
aggregate_version
correlation_id
causation_id?
actor_type
actor_id?
source
code_release
payload
```

Rules:

- Event IDs are globally unique; consumers deduplicate them.
- Aggregate versions define order. Consumers buffer/reconcile bounded gaps and never apply an older
  event over a newer projection.
- Payloads reference immutable evidence rather than copying secrets, private reasoning, or full
  source documents.
- Schema evolution is backward compatible within a major family. Breaking changes publish a new
  schema version and migration/dual-read plan.
- At-least-once delivery is assumed. Every consumer is idempotent.

## Security and Configuration Events

- `user.email_verified`
- `user.mfa_enrolled`, `user.mfa_replaced`, `user.recovery_code_used`
- `session.created`, `session.revoked`, `step_up.verified`
- `credential.created`, `credential.replaced`, `credential.tested`, `credential.disabled`
- `connection.health_changed`
- `instrument_mapping.verified`, `instrument_mapping.stale`, `instrument_specification.activated`
- `futures_chain.recorded`, `futures_contract.roll_required`, `futures_contract.expired`
- `corporate_action.recorded`, `financing_terms.changed`
- `model.changed`, `model_profile.changed`
- `agent_configuration.activated`, `agent_runtime.selection_changed`, `prompt_version.activated`,
  `agent.test_completed`

Secret events contain only credential reference, masked suffix, provider purpose and audit metadata.
Agent runtime events contain previous/new runtime, selection source, configuration/profile version,
actor, and reason. Connecting LiteLLM or synchronizing its models does not emit a selection change;
only explicit configuration activation can change an agent from the Codex default.

## Autonomous Research Events

- `research.queued`, `research.started`, `research.degraded`, `research.completed`, `research.failed`
- `research_lane.started`, `research_lane.ready`, `research_lane.no_trade`,
  `research_lane.not_configured`, `research_lane.unavailable`, `research_lane.stale`,
  `research_lane.blocked`
- `market_selection.selected`
- `market_selection.invalidated`
- `market_selection.fallback_selected`
- `market_selection.no_trade`
- `market_selection.expired`

Every lane payload identifies `(asset_class, instrument_type)`, the matrix/run version, provider
binding and source-cut references, terminal state, and—when ready—the immutable candidate, exact
venue listing or dated futures contract, and specification version. `research.completed` summarizes
all 12 terminal lane results and cannot imply that a non-ready lane produced a recommendation.
Fallback stays within the original lane and creates a new selection version. Mapping/specification
changes, futures expiry/roll, corporate actions, and financing-term changes invalidate affected
selections and Trade Plans rather than silently rewriting them.

## Strategy Events

- `strategy_draft.created`, `strategy_rule.revised`
- `strategy_assistance.requested`, `strategy_suggestion.created`
- `strategy_suggestion.accepted`, `.edited`, `.rejected`
- `strategy_completeness.evaluated`
- `strategy_similarity.evaluated`, `strategy_duplicate.blocked`
- `strategy_version.created`, `strategy_implementation.completed`
- `backtest.completed`, `validation_stage.completed`, `paper_run.completed`
- `strategy.promotion_decided`, `strategy.activated`
- `strategy.health_changed`, `strategy.research_requested`

Events reference draft/version revision, actor/agent execution, accepted rule revisions, schema/code
versions and validation evidence. Conversation prose alone never emits `strategy_rule.revised`.

## Policy, Risk, Permission, and Trade Plan Events

- `ruleset.verified`, `ruleset.activated`, `guardrail_profile.activated`
- `account_snapshot.recorded`
- `policy.evaluated`, `risk.evaluated`
- `risk_reservation.created`, `.converted`, `.released`, `.expired`
- `execution_permission.activated`, `.replaced`
- `kill_switch.activated`, `.deactivated`, `.dispatch_blocked`
- `trade_plan.created`, `.reduced`, `.validated`, `.authorized`, `.blocked`, `.expired`, `.cancelled`

`risk.evaluated` contains immutable context/result IDs and status. HARD_BLOCK never emits
`trade_plan.authorized`. Permission and kill events carry scope, version/safety epoch, actor, reason,
and step-up audit reference without secrets.

## Execution, Broker, and Trade Events

- `execution_command.created`, `.dispatching`, `.submitted`, `.acknowledged`, `.rejected`,
  `.outcome_unknown`, `.reconciling`, `.reconciled`, `.blocked_ambiguous`, `.superseded`
- `broker.order_accepted`, `.rejected`, `.cancelled`, `.expired`
- `broker.fill_partial`, `.completed`, `.corrected`
- `broker.position_opened`, `.changed`, `.closed`, `.external_activity_detected`
- `broker.stop_loss_changed`, `.take_profit_changed`, `.protection_executed`
- `broker.account_changed`, `broker.connection_stale`, `.restored`
- `reconciliation.started`, `.confirmed`, `.no_effect_confirmed`, `.blocked_ambiguous`, `.failed`
- `trade.position_activated`, `trade.monitoring_updated`
- `management_action.proposed`, `.authorized`, `.blocked`, `.submitted`, `.reconciled`
- `trade.closed`, `trade.journaled`

Execution payloads reference Trade Plan, command, authorization, permission version, platform/account
safety epochs, exact target, expected broker version, certainty, and reconciliation state. Broker
payloads preserve provider IDs, sequence and source times; acceptance, fill, and position are distinct
facts. Broker protection execution may close the trade directly. An ambiguous match blocks autonomous
management and never becomes confirmed by inference.

## Knowledge and Operations Events

- `knowledge_source.created`, `.disabled`, `.deletion_requested`, `.deleted`
- `knowledge_ingestion.started`, `.completed`, `.failed`
- `knowledge_index.degraded`, `.restored`
- `journal.event_committed`, `.observation_requested`, `.observation_appended`, `.observation_failed`
- `journal.index_requested`, `.indexed`, `.index_retry_scheduled`, `.index_failed`
- `journal.summary_requested`, `.summary_created`, `.summary_indexed`, `.summary_failed`
- `knowledge_assistant.answered`, `.partial`, `.insufficient`, `.refused`
- `performance.observation_recorded`, `.population_materialized`, `.metrics_calculated`,
  `.edge_assessed`, `.rollup_degraded`, `.rollup_restored`
- `trade_entry.confirmed`, `trade_entry_notification.created`, `.status_updated`
- `notification.delivery_requested`, `.delivered`, `.retry_scheduled`, `.failed`, `.unknown`
- `chart.source_degraded`, `.source_restored`
- `job.started`, `.retry_scheduled`, `.completed`, `.failed`
- `service.health_changed`, `circuit_breaker.opened`, `.closed`

Deletion events keep a tombstone but not deleted content. Knowledge degradation never implies that
current risk or policy is unavailable. Journal commits precede indexing. Knowledge Assistant events
store query digest/retrieval audit and answer status without unnecessary sensitive text. Trade-entry
notification events reference committed broker acceptance/fill evidence and a root dedupe identity;
unconfirmed submissions emit none. Chart interactions emit no trading-domain event.

## UI Event Projection

Authenticated SSE exposes owner-scoped projections with last-event resume IDs. User-visible states
include `RESEARCHING`, `EXECUTING`, `RECONCILING`, `OUTCOME_UNKNOWN`, `ACTIVE`, `BLOCKED`,
`DEGRADED`, `KILL_SWITCH_ACTIVE`, and `OFFLINE`.
The UI must re-fetch aggregate state after reconnect or version gaps rather than reconstructing
financial truth solely from the event stream.

## Contract Tests

- Duplicate delivery produces one projection/mutation.
- Out-of-order versions never roll state backward.
- Missing versions trigger bounded recovery and authoritative re-fetch.
- Cross-owner/account events are never delivered or consumed outside scope.
- Payload validation rejects secrets, raw prompt credentials, and unsupported schema versions.
- Execution-command, risk-reservation, journal-index, notification, and broker-event replay remains idempotent.
- A 12-lane research run emits exactly one terminal lane fact per requested lane; duplicate terminal
  delivery is idempotent and cross-instrument-type fallback is rejected.
- Continuous futures identifiers are rejected from executable selection and Trade Plan events.
- Permission and kill-switch races cannot dispatch with stale versions/epochs.
- An uncertain command cannot retry before a reconciliation fact proves no effect.
- Duplicate/out-of-order fills cannot create duplicate positions or entry notifications.
- Knowledge Assistant trading prompts emit `refused` and no execution event.
- Chart interaction emits no Trade Plan, command, or broker event.
