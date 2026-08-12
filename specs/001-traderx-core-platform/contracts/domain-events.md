# TraderX Domain Event Contract

## Delivery Semantics

Domain events are durable facts, not Celery task payloads. The aggregate mutation, audit record,
and outbox event commit in one PostgreSQL transaction. The dispatcher provides at-least-once
delivery; each consumer records an inbox receipt before acknowledging completion. Consumers MUST
be idempotent. Ordering is guaranteed only within one aggregate through `aggregateversion`.

An event that repeatedly fails becomes visibly `FAILED` with its attempts and redacted error. It
is never silently deleted. Redis transports work but is not the event ledger.

## Envelope

The JSON envelope follows CloudEvents 1.0 conventions:

```json
{
  "specversion": "1.0",
  "id": "0198...",
  "source": "urn:traderx:accounts",
  "type": "com.traderx.risk.circuit-breaker-activated.v1",
  "subject": "accounts/{account_id}/circuit-breakers/{breaker_id}",
  "time": "2026-08-12T10:30:00.000000Z",
  "datacontenttype": "application/json",
  "dataschema": "/contracts/events/risk/circuit-breaker-activated.v1.json",
  "correlationid": "0198...",
  "causationid": "0198...",
  "actorid": "0198...",
  "aggregateversion": 7,
  "traceparent": "00-...",
  "data": {}
}
```

Rules:

- `source + id` is globally unique and is the consumer deduplication key.
- Event names and payload schemas are immutable. Breaking changes create `.v2`, never mutate `.v1`.
- `data` contains stable identifiers, reason codes, states, and safe evidence references—not
  credentials, full provider secrets, session tokens, or unredacted sensitive payloads.
- Events describe completed facts. Commands and requests use the HTTP contract.
- Consumers retrieve large artifacts by authorized reference rather than embedding them.

## Event Catalog

### Identity and Security

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.identity.initial-owner-created.v1` | user, bootstrap state, time | audit, security monitoring |
| `com.traderx.identity.user-authenticated.v1` | user, session, assurance, time | audit, security monitoring |
| `com.traderx.identity.session-revoked.v1` | user, session, reason | UI stream, security monitoring |
| `com.traderx.identity.mfa-changed.v1` | user, action | audit, notifications |
| `com.traderx.identity.mfa-recovery-used.v1` | user, recovery code identity, reset outcome | audit, security monitoring |
| `com.traderx.identity.password-reset-completed.v1` | user, reset challenge, proof kind | audit, security monitoring |
| `com.traderx.identity.assisted-mfa-reset.v1` | target user, actor, reason, outcome | audit, security monitoring |
| `com.traderx.identity.authorization-denied.v1` | actor, action, target, reason | audit, security monitoring |

### Accounts and Risk

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.account.snapshot-recorded.v1` | account, snapshot, provider time, quality | risk projection, dashboard |
| `com.traderx.risk.snapshot-calculated.v1` | account, snapshot, state, capacity, reasons | dashboard, opportunity engine |
| `com.traderx.risk.state-changed.v1` | account, from/to, evidence | alerts, audit, monitoring |
| `com.traderx.risk.decision-recorded.v1` | decision, opportunity, outcome, permitted risk, reasons | recommendation engine, audit |
| `com.traderx.risk.circuit-breaker-activated.v1` | breaker, scope, evidence | recommendation blocker, alerts, audit |
| `com.traderx.risk.circuit-breaker-cleared.v1` | breaker, actor, reason | dashboard, alerts, audit |
| `com.traderx.risk.policy-version-created.v1` | account, policy version, actor, reason | risk projection, audit |

### Integrations and Market Data

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.integration.health-changed.v1` | integration, from/to, affected capabilities, reason | dashboard, circuit breakers, alerts |
| `com.traderx.integration.credential-rotated.v1` | integration, credential version, actor | audit, connection tester |
| `com.traderx.marketdata.batch-ingested.v1` | batch/manifest, coverage, quality | normalization, jobs |
| `com.traderx.marketdata.quality-failed.v1` | instrument/provider, scope, policy, reasons | quarantine, circuit breakers, alerts |
| `com.traderx.broker.position-observed.v1` | account, position, revision, reconciliation state | risk, matching, monitoring, journal |
| `com.traderx.broker.deal-observed.v1` | account, position, deal identity | position projection, journal |
| `com.traderx.broker.reconciliation-required.v1` | account, gap/contradiction evidence | integration health, risk blocker |

### Market Selection

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.markets.research-completed.v1` | run, category, methodology, eligible count | UI, alerts |
| `com.traderx.markets.candidate-ineligible.v1` | run, instrument, failed gates | report/audit |
| `com.traderx.markets.active-assignment-approved.v1` | category, instrument, assessment, actor, reason | active-universe projection, audit |
| `com.traderx.markets.active-assignment-ended.v1` | category, instrument, reason | strategy/opportunity eligibility, audit |
| `com.traderx.markets.replacement-recommended.v1` | current/candidate assessments, rationale | UI, notification only; never auto-assigns |

### Research, Strategy, and Validation

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.research.job-completed.v1` | job, instrument, result/artifact references | Strategy Lab, alerts |
| `com.traderx.strategy.version-created.v1` | strategy/version, parent, definition hash | lifecycle, audit |
| `com.traderx.strategy.lifecycle-changed.v1` | version, from/to, evidence, actor/system | UI, audit, eligibility projections |
| `com.traderx.validation.run-completed.v1` | run, version, type, outcome, evidence | lifecycle gate, alerts |
| `com.traderx.paper.run-completed.v1` | run, version, outcome, comparison | lifecycle gate, alerts |
| `com.traderx.strategy.approval-decided.v1` | version, decision, actor, assurance, reason | lifecycle, audit, alerts |
| `com.traderx.strategy.health-changed.v1` | version, from/to, reasons | opportunity eligibility, alerts |

### Opportunities and Trades

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.opportunity.assessed.v1` | opportunity, state, score, evidence | rank projection, UI |
| `com.traderx.recommendation.issued.v1` | recommendation, risk decision, expiry | UI, alerts, audit |
| `com.traderx.recommendation.expired.v1` | recommendation, reason | UI, alerts |
| `com.traderx.position.classified.v1` | position, classification, match, actor | risk, thesis, journal, audit |
| `com.traderx.trade.thesis-frozen.v1` | position, thesis, content hash | monitor, journal |
| `com.traderx.trade.health-changed.v1` | position, from/to, reasons, guidance | UI, alerts, journal |
| `com.traderx.trade.closed.v1` | position, execution summary, outcome | journal, strategy health, analytics |

### Jobs and Notifications

| Event type | Minimum data | Primary consumers |
|---|---|---|
| `com.traderx.job.state-changed.v1` | job, attempt, from/to, progress | UI SSE, audit where material |
| `com.traderx.notification.created.v1` | notification, topic, severity, recipients | router |
| `com.traderx.notification.delivery-completed.v1` | notification, channel, outcome, provider identity | operations UI |

## Idempotent Consumer Rules

1. Start a transaction and insert `(consumer_name, event_source, event_id)` into the inbox.
2. If the unique insert conflicts, return success without replaying side effects.
3. Validate schema version and aggregate ordering.
4. Apply the projection/effect, write any new outbox events, and mark the receipt completed.
5. Commit before acknowledging delivery.

Consumers MUST NOT infer financial authority from delivery order across aggregates. The Risk
Manager re-reads authoritative account, position, policy, and data-quality state in one decision
transaction.

## Audit Relationship

Domain events and audit records are related but not interchangeable. Audit adds actor role,
session/authentication strength, source channel, attempted action, outcome, mandatory reason,
redacted before/after values, request and idempotency identity. If audit is mandatory and cannot
commit, the high-risk command fails closed.
