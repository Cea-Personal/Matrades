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
- `model.changed`, `model_profile.changed`
- `agent_configuration.activated`, `agent_runtime.selection_changed`, `prompt_version.activated`,
  `agent.test_completed`

Secret events contain only credential reference, masked suffix, provider purpose and audit metadata.
Agent runtime events contain previous/new runtime, selection source, configuration/profile version,
actor, and reason. Connecting LiteLLM or synchronizing its models does not emit a selection change;
only explicit configuration activation can change an agent from the Codex default.

## Research and HIL-1 Events

- `research.queued`, `research.started`, `research.degraded`, `research.completed`, `research.failed`
- `market_selection.approval_requested`
- `market_selection.approved`
- `market_selection.replaced`
- `market_selection.rerun_requested`
- `market_selection.expired`

The payload identifies research run/version, ranked candidates/evidence references and exact action.
REPLACE creates a new selection version; RERUN creates a new research run.

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

## Policy, Risk, and Proposal Events

- `ruleset.verified`, `ruleset.activated`, `guardrail_profile.activated`
- `account_snapshot.recorded`
- `policy.evaluated`, `risk.evaluated`
- `risk_reservation.created`, `.converted`, `.released`, `.expired`
- `trade_proposal.blocked`, `.reduced`, `.approval_requested`, `.expired`
- `trade_proposal.take_recorded`, `.wait_recorded`, `.rejected`

`risk.evaluated` contains the immutable context/result IDs and result status. HARD_BLOCK never emits
`trade_proposal.approval_requested`. TAKE carries its reservation to awaiting manual entry.

## Broker, Trade, and HIL-3 Events

- `broker.position_opened`, `.changed`, `.closed`
- `broker.stop_loss_changed`, `.take_profit_changed`, `.protection_executed`
- `broker.account_changed`, `broker.connection_stale`, `.restored`
- `reconciliation.candidate_found`, `.confirmation_requested`, `.confirmed`, `.rejected`
- `trade.position_activated`, `trade.monitoring_updated`
- `trade_management.approval_requested`
- `trade_management.approved`, `.wait_recorded`, `.rejected`
- `trade.closed`, `trade.journaled`

Broker event payloads preserve provider event/sequence and source times. HIL-3 applies only to a
recommended discretionary change; broker protection execution may close the trade directly.

## Knowledge and Operations Events

- `knowledge_source.created`, `.disabled`, `.deletion_requested`, `.deleted`
- `knowledge_ingestion.started`, `.completed`, `.failed`
- `knowledge_index.degraded`, `.restored`
- `notification.delivery_requested`, `.delivered`, `.failed`
- `job.started`, `.retry_scheduled`, `.completed`, `.failed`
- `service.health_changed`, `circuit_breaker.opened`, `.closed`

Deletion events keep a tombstone but not deleted content. Knowledge degradation never implies that
current risk or policy is unavailable.

## UI Event Projection

Authenticated SSE exposes owner-scoped projections with last-event resume IDs. User-visible states
include `RESEARCHING`, `WAITING`, `ACTION_REQUIRED`, `ACTIVE`, `BLOCKED`, `DEGRADED`, and `OFFLINE`.
The UI must re-fetch aggregate state after reconnect or version gaps rather than reconstructing
financial truth solely from the event stream.

## Contract Tests

- Duplicate delivery produces one projection/mutation.
- Out-of-order versions never roll state backward.
- Missing versions trigger bounded recovery and authoritative re-fetch.
- Cross-owner/account events are never delivered or consumed outside scope.
- Payload validation rejects secrets, raw prompt credentials, and unsupported schema versions.
- Approval, risk-reservation and broker-event replay remains idempotent.
