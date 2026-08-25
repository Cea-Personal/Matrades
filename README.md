# Matrades

Matrades is Codex-first, human-in-the-loop multi-market trading decision support. It researches Forex, metals, and crypto; validates strategies; computes equity-aware risk; and reconciles manually entered MT5 trades. V1 contains no broker-write capability.

## Local setup

Requirements: Python 3.13 with `uv`, Node 24/npm 11, Docker Compose. Copy `.env.example` to `.env` and replace development secrets with test-only values.

```bash
make bootstrap
docker compose -f infra/compose/compose.yaml up --build postgres redis api worker scheduler agent-worker web
make migrate
make seed
make test
```

The local `agent-worker` installs the official Codex CLI and mounts
`${HOME}/.codex/auth.json` into the container. Run `codex login` on the host first, or
use an API-key authentication strategy for a non-local deployment. Never commit the
Codex authentication cache.

LiteLLM is optional and never a fallback from Codex:

```bash
docker compose -f infra/compose/compose.yaml --profile litellm up litellm
```

After connecting it, explicitly create a LiteLLM-bound model profile and assign individual agents. Unassigned agents remain on Codex App Server.

API docs are at `http://localhost:8000/docs`; the web UI is at `http://localhost:3000`. Use fixture/test credentials only. For troubleshooting, inspect `/api/v1/operations/health`: stale authoritative inputs intentionally cause BLOCK, WAIT, DEGRADED, or NO TRADE.

## Connections and MT5

Open **Connections** in the main navigation. First save an encrypted credential when a provider
requires one, then create a named connection for Twelve Data, Coinbase, CoinGecko, FRED, a
calendar/news HTTPS endpoint, or the MT5 Bridge. **Test** performs a real bounded health probe and
records capabilities, freshness, and latency; an untested connection is never assumed healthy.

For MT5, run the read-only bridge against a demo account, store its HMAC secret as an MT5 Bridge
credential, then create a connection with the bridge URL and account reference. Local development
may use `http://127.0.0.1:8765`; remote bridge URLs must use HTTPS. Matrades checks that the bridge
advertises no write capability and never exposes an order-write action.

## Autonomous research

The scheduler starts one daily research cycle per configured trading account. It scans the
configured Forex, metals, and crypto universes, then the bounded research and analyst agents
review deterministic fingerprints before HIL-1. The Research UI does not require initial pair
entry; manual symbols are accepted only as an explicit **Replace** decision.

Forex and metals discovery requires an active Twelve Data connection configured in **Connections**.
Crypto discovery uses an active public Coinbase connection. Configure each provider-owned universe
on its connection profile and configure the UTC schedule in `.env`.
If a category provider or required agent is unavailable, the persisted run becomes `DEGRADED`
and Matrades does not fabricate that category's recommendation.

Every successful, degraded, or failed market-research cycle is saved below
`data/research_cycles/<owner>/market_research/<year>/<month>/<day>/`. Strategy research and
backtests use sibling timestamped folders. Each immutable `manifest.json` includes the cycle ID,
UTC timestamp, evidence details, and checksum; the Research and Strategy screens link the durable
run metadata to these archives. Docker persists the folder in the `research-artifacts` volume.

## Strategy generation and validation

The Strategy Lab exposes exactly two origins. **AI Generated** asks `strategy_researcher` to choose
a family and build a complete strategy. **AI Assisted** requires your description and asks
`strategy_assistant` to flesh it out. Both show the family and step-by-step proposal first; only
**Approve strategy** copies the proposal into the canonical repository.

After approval and submission, choose a strategy version and a tested Twelve Data or Coinbase
connection in **Provider backtest & validation**. Configure the instrument, chronological window,
timeframe, equity, spread, commission, slippage, and loss limits. The worker fetches provider
candles, applies next-bar point-in-time execution, persists the backtest and archive manifest, and
shows backtest, out-of-sample, walk-forward, stress, and policy gates. A passing backtest does not
bypass the separate paper-trading and promotion requirements.

## Authentication

Open `http://localhost:3000/auth` and select **Sign up**. In development, the UI displays the generated email-verification token; production deployments must deliver that token through the configured notification provider. After verification, scan or enter the TOTP secret, save the one-time recovery codes, and confirm a current six-digit code. The server then creates an eight-hour HttpOnly session cookie.

Every later login requires the password plus TOTP or an unused recovery code. **Forgot password?** starts the recovery flow; completing it revokes every existing session. Sensitive credential changes also require a recent MFA step-up from Configuration → Security. Authentication and owner identity come exclusively from the server session—not request headers or browser-supplied owner IDs.
