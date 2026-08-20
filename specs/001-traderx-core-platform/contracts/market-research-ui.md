# TraderX Market Research UI Contract

## Scope

Market-data integrations, the global research-model selector, recurring schedule, coordinated run
history, evidence reports, and activation/replacement approval live inside the existing authenticated
TraderX Command Center. They are not a second application or separate workspace.

## Integration Catalogue

The Integrations panel presents only reviewed catalogue cards. Each card shows provider, adapter and
catalogue revision, asset/venue coverage, capabilities, actual/proxy semantics, required entitlement,
retention/licensing notice, configuration status, health, last success, and freshness.

An authorized owner can connect, test, enable, disable, rotate credentials, and remove CME Group,
Cboe FX Spot, Coinbase Exchange, OpenAI, Anthropic, and LiteLLM Gateway integrations. Credentials are write-only on
entry and masked thereafter. Arbitrary URLs and provider keys are never accepted.

## Global LLM Model Control

The Markets workspace displays one global provider selector containing healthy configured direct
providers and LiteLLM Gateway connections, plus an exact model-ID input. An owner may enter a
compatible direct model ID or a LiteLLM model alias exposed by the selected healthy integration.

The selector shows exact provider/model, health, catalogue revision, retention posture, estimated
pricing basis, and “applies to future runs” guidance. Saving requires owner authorization, a reason,
and optimistic concurrency. An active run continues with its pinned model.

## Recurring Schedule

The owner can configure an interval from one hour through 30 days, anchored local start, account
time zone, enabled state, and next regular occurrence. The UI displays the last occurrence and each
`SKIPPED_OVERLAP` fact. It never offers concurrent or catch-up execution.

Manual **Run all three markets** and scheduled execution create one coordinated parent with exactly
one Commodity, Forex, and Cryptocurrency result. Closing the browser does not stop work.

## Results and Evidence

The run view shows:

- parent state and three independently completable category outcomes;
- evaluated MT5 broker universe and every exclusion reason;
- provider, venue, instrument mapping, capability, `ACTUAL`/`BROKER_PROXY`/`UNAVAILABLE`, observed
  time, age, freshness policy, and quality/conflict state for every liquidity measure;
- specialist retry and ordered MT5/cached-external fallback trail;
- deterministic methodology, metrics, components, score, rank, and selection proposal;
- pinned LLM provider/model/catalogue/prompt/schema/inference versions;
- advisory analysis or a visible unavailable/refused/invalid/timed-out/rate-limited reason; and
- eligibility for explicit same-pinned-model analysis retry.

`ranking_is_not_activation` is always visible. A recommendation is followed by a separate
authorized confirmation flow; a blocked category preserves the current active assignment.

## Required UI States

Every panel has accessible loading, empty, healthy, stale, conflicting, rate-limited,
provider-disabled, entitlement-missing, model-retired, analysis-unavailable, permission-denied,
failed, and retrying states. Failures retain the last valid evidence for audit but never present it
as current unless its unchanged freshness policy still passes.

Status is conveyed by text and semantics, not colour alone. Controls are keyboard reachable,
focus returns to the initiating control or resulting heading, asynchronous changes use an ARIA live
region, tables have headers/captions, and error text identifies the affected category/source/model
and a valid next action.

## Test Oracles

1. No arbitrary source/model can be entered or selected.
2. Disabling/rotating a provider updates health without exposing its secret.
3. One due time yields one parent job or one overlap skip after browser closure/restart.
4. Every category displays its asset-specific evidence and source semantics.
5. MT5-unsupported candidates never become eligible from external evidence.
6. Fallback never extends freshness or weakens a mandatory gate.
7. Model changes affect only future runs; explicit analysis retry uses the pinned model.
8. Any LLM output/failure leaves deterministic gates, metrics, scores, ranks, and proposals
   unchanged.
9. No result activates or replaces a market without separate human approval.
