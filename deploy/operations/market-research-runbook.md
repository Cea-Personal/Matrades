# Market Research Operations Runbook

TraderX market research is decision support. It never activates a market, promotes a strategy,
or submits an order. A failure in required source evidence blocks the affected category and
preserves its current active assignment.

## Provider prerequisites

Use the authenticated **Account connection → Reviewed research providers** panel. Production
operators may select only the code-reviewed catalogue entries:

| Category | Primary source | Required prerequisite |
|---|---|---|
| Commodity | CME Group | Contracted API access plus display, use, and retention entitlements |
| Forex | Cboe FX Spot | Venue-data access and explicit entitlement; this is not a consolidated FX book |
| Cryptocurrency | Coinbase Exchange | Official Exchange API terms and retention review |
| Advisory analysis | OpenAI Responses or Anthropic Messages | Qualified project credential and one allowlisted exact model |
| Broker authority/proxy | Native MT5 EA | Enrolled account/server, investor mode, trading disabled, complete fresh snapshot |

Record legal/licensing approval outside TraderX, acknowledge the notice in the UI, and retain the
approval reference in the deployment change record. An acknowledgement does not create an
entitlement. CME/Cboe stay `DEGRADED` until an operator verifies the entitlement evidence.

## Credential lifecycle

Credentials are entered once and returned only as `WRITE_ONLY`. TraderX encrypts each version with
AES-256-GCM envelope encryption. To rotate, open the provider card, enter the complete new
provider-specific secret set, confirm the effect, and test qualification. The prior version is
revoked before the integration can return to `HEALTHY`. If testing fails, leave the integration
`DEGRADED` or `DISABLED`; do not restore a stale credential from logs or screenshots.

On suspected exposure, disable the integration, revoke the provider credential at the provider,
rotate it in TraderX, qualify every advertised capability, and review redacted audit/health facts.
Removing an integration revokes its active credential while retaining historical evidence.

## Symbol mapping approval

1. Refresh the MT5 broker instrument catalogue.
2. Discover instruments from the reviewed specialist source.
3. Match the exact venue product/contract to the MT5 symbol. Commodity futures month/contract and
   broker CFD variants require explicit contract-variant evidence.
4. Verify entitlement, catalogue revision, provider venue, and MT5 broker support.
5. An MFA-assured owner approves the mapping and reason. Ambiguous, unsupported, expired, or
   unentitled mappings remain unavailable.

External coverage never overrides MT5’s broker-support veto. A provider-symbol string match alone
is not sufficient evidence.

## Schedule and worker recovery

PostgreSQL owns the anchored interval, IANA time zone, next due time, unique occurrence, lease,
and overlap outcome. Celery Beat wakes `traderx.market_rotation.scan_due` every 60 seconds; it does
not own the schedule. A due occurrence creates one parent and exactly three category children.
If a prior parent is active, record `SKIPPED_OVERLAP`, advance to the next anchored occurrence,
and do not catch up.

For a stalled run:

1. Inspect Operations → Jobs, schedule status, worker health, occurrence lease, and outbox facts.
2. Restore database/Redis/worker connectivity without editing the next due time manually.
3. Let the scanner recover only an expired lease; replaying the same due time must return the same
   occurrence/parent.
4. Resume incomplete category checkpoints independently. Never create a fourth child.
5. Confirm completion/partial outcome and that all active assignments are unchanged.

## Source outage and fallback

The immutable path is three bounded specialist attempts, current complete MT5 evidence, the most
recent successful external evidence within its original freshness policy, then `BLOCKED`. Do not
extend an age limit, substitute an unreviewed provider, treat unavailable fields as zero, or weaken
an asset-specific gate during an outage. Contradictory evidence is quarantined.

Review source role, provider/venue, `ACTUAL`/`BROKER_PROXY`/`UNAVAILABLE` semantics, observed age,
policy version, mapping revision, entitlement, conflict state, and raw-evidence hash in Markets.
Notify the owner on entitlement loss, material conflict, stale required evidence, repeated schedule
failure, or blocked category.

## Model failure or retirement

One global selection applies to future runs. Each parent pins provider, exact model, catalogue,
adapter, prompt, schema, and inference-policy revisions atomically. A running or completed run
never changes pins after a global update.

On rate limit, invalid output, refusal, timeout, authentication failure, or outage, TraderX makes at
most three bounded attempts against the same model. Exhaustion displays `UNAVAILABLE`; deterministic
gates, metrics, scores, ranks, and proposals remain unchanged. An explicit retry uses the original
pin and never substitutes another model. For a retired model, disable it for future selection,
retain historical pins/results, qualify a reviewed replacement, then update the global selection.

## Release and incident evidence

Retain provider catalogue/policy revisions, source manifests and hashes, occurrences, coordinated
runs, LLM attempts/usage, health observations, audit events, notifications, and outbox facts. Before
enabling production research, run the contract, data-quality, safety, security, scheduler,
acceptance, performance, web unit/type/lint/build, and browser accessibility suites documented in
the feature quickstart. Browser-test evidence is mandatory even though research execution itself
must continue with the browser closed.
