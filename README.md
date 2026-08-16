# TraderX

TraderX is a conservative research, risk, paper-trading, and manual-trade decision-support
platform. It never submits or modifies real-money orders.

## Install

Use Python 3.13 and Node 24:

```sh
uv sync --all-groups
cd apps/web && npm install
```

For local containers, create `deploy/secrets/postgres_password` with a local-only database
password, then run `docker compose -f deploy/compose.yaml up --build`.

When the stack is ready, open **https://localhost:3000**. Caddy creates a local development
certificate, so the browser will show a certificate warning on first use; proceed only for this
local TraderX instance. The API is intentionally private: use
`https://localhost:3000/api/v1/docs` through the proxy rather than `localhost:8000`.
For a local MT5 Expert Advisor on macOS/Wine, use **https://127.0.0.1:3000** in its WebRequest
allow-list and as the EA API origin; it uses the same local proxy with an IP-specific certificate.

Apply migrations after pulling a newer TraderX version and before restarting the API/workers:

```sh
docker compose -f deploy/compose.yaml run --rm migrate
docker compose -f deploy/compose.yaml up -d --build
```

## Owner bootstrap and operation

Create the first owner through the governed identity bootstrap path, enroll MFA, configure one
primary account, prop limits, stricter internal limits, then review the Command Center. Manage
integrations, jobs, notifications, audit history, and health only through authenticated UI routes.
Secrets are write-only and encrypted.

Before the safety checklist is complete, the Command Center shows only the required onboarding
work. After a complete verified MT5 snapshot satisfies the final account-data gate, onboarding is
replaced by one integrated TraderX workspace with these tabs:

- **Markets** — import the MT5 instrument catalog, run eligibility-first research, inspect every
  exclusion, and explicitly approve or replace one market in each category.
- **Strategies** — define no-code rules, create immutable versions, and run chronological
  backtest and validation evidence.
- **Paper trading** — run current-data simulated evaluation, compare it with historical evidence,
  and make an explicit MFA-backed approval, rejection, or return-to-research decision.
- **Opportunities** — evaluate live-approved strategies and inspect scoring separately from the
  shared-account Risk Manager decision and complete manual-only recommendation.
- **Trade monitoring** — refresh MT5 positions, correct classification with an audit record, and
  inspect the frozen thesis and append-only health timeline.
- **Journal** — project completed activity, append behavioral notes and protected screenshots,
  compare financial/R outcomes, and create evidence-linked research proposals.
- **Operations** — manage durable jobs, notification preferences, system/integration/strategy
  health, circuit breakers, and redacted audit evidence.

There is one **Account connection** tab for managing the MT5 read-only integration. Sign out from
the authenticated navigation at the top of the page.

## MetaTrader 5 account evidence

MetaTrader 5 is TraderX's only supported broker-account integration.

TraderX manages the MT5 bridge enrollment from Command Center. Enter the MT5 account login and
broker server there; TraderX produces a short-lived setup code for its read-only MT5 Expert
Advisor. Install that EA into MT5 on macOS or Windows and let it supply outbound account snapshots
every 15 seconds. The MT5 investor password stays in MT5. You do not enter a bridge URL, bridge
identity, or bridge credential in TraderX. See [the MT5 bridge guide](apps/mt5_bridge/README.md)
for the operational details.

## Automated market research

Market research is configured inside the existing **Markets** workspace. It always coordinates
one Commodity, one Forex, and one Cryptocurrency category run. Set an interval from one hour to
30 days, an anchored local start, and an IANA account time zone. PostgreSQL owns the next due time,
so closing the browser does not stop research. If the preceding coordinated run is still active,
TraderX records an overlap skip and does not create catch-up runs.

Before enabling the schedule, use **Account connection → Reviewed research providers** to connect
and qualify the fixed sources:

- CME Group for Commodity venue volume, open interest, and entitled book evidence;
- Cboe FX Spot for venue-specific Forex prints/volume/book evidence;
- Coinbase Exchange for Cryptocurrency venue volume and order-book evidence; and
- either OpenAI Responses (`gpt-5.6-terra`) or Anthropic Messages (`claude-sonnet-5`) for optional
  advisory explanation.

Provider licensing, entitlement, and retention prerequisites remain the operator’s responsibility.
Credentials are encrypted and write-only. Arbitrary providers, URLs, and model IDs are rejected.
MT5 remains the authority for broker support and provides explicitly labelled broker activity,
spread, real-volume-when-available, and Depth of Market proxy evidence.

The source trail is specialist (up to three bounded attempts), then current complete MT5, then a
cached external success only while it remains inside the original freshness policy. Missing,
stale, partial, contradictory, unentitled, or unsupported evidence blocks the affected category;
it never becomes zero and never changes the current active market.

The selected LLM applies only to future runs. Each run pins its exact provider/model and related
catalogue, adapter, prompt, schema, and inference versions. Analysis cannot change deterministic
gates, metrics, scores, ranks, or proposals. If analysis is unavailable, use **Retry pinned
analysis** to retry the same model; TraderX never substitutes a different model automatically.
After reviewing all eligibility and provenance evidence, **Review for activation** begins a
separate deliberate human approval. A ranking alone never activates or replaces a market.

Operator procedures for entitlement, mapping approval, outages, rotation, model retirement, and
scheduler recovery are in
[deploy/operations/market-research-runbook.md](deploy/operations/market-research-runbook.md).

## Safety boundary

TraderX researches one human-approved Commodity, Forex, and Cryptocurrency market; validates
immutable strategy versions; paper trades; issues expiring, risk-approved recommendations; and
monitors positions opened manually at the broker. It does not execute orders, scrape providers,
or auto-promote strategies or markets.

Run the complete local verification gates with:

```sh
.venv/bin/pytest -q
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web test -- --run
npm --prefix apps/web run test:e2e
npm --prefix apps/web run build
```

Production hardening and recovery procedures are in
[deploy/operations/runbook.md](deploy/operations/runbook.md). A passing development suite is not
authorization to deploy or to place a trade.
