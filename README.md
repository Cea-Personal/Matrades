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

## Owner bootstrap and operation

Create the first owner through the governed identity bootstrap path, enroll MFA, configure one
primary account, prop limits, stricter internal limits, then review the Command Center. Manage
integrations, jobs, notifications, audit history, and health only through authenticated UI routes.
Secrets are write-only and encrypted.

## MetaTrader 5 account evidence

MetaTrader 5 is TraderX's only supported broker-account integration.

TraderX manages the MT5 bridge enrollment from Command Center. Enter the MT5 account login and
broker server there; TraderX produces a short-lived setup code for its read-only MT5 Expert
Advisor. Install that EA into MT5 on macOS or Windows and let it supply outbound account snapshots
every 15 seconds. The MT5 investor password stays in MT5. You do not enter a bridge URL, bridge
identity, or bridge credential in TraderX. See [the MT5 bridge guide](apps/mt5_bridge/README.md)
for the operational details.

## Safety boundary

TraderX researches one human-approved Commodity, Forex, and Cryptocurrency market; validates
immutable strategy versions; paper trades; issues expiring, risk-approved recommendations; and
monitors positions opened manually at the broker. It does not execute orders, scrape providers,
or auto-promote strategies or markets.
