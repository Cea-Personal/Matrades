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

## Owner bootstrap and operation

Create the first owner through the governed identity bootstrap path, enroll MFA, configure one
primary account, prop limits, stricter internal limits, then review the Command Center. Manage
integrations, jobs, notifications, audit history, and health only through authenticated UI routes.
Secrets are write-only and encrypted.

## Safety boundary

TraderX researches one human-approved Commodity, Forex, and Cryptocurrency market; validates
immutable strategy versions; paper trades; issues expiring, risk-approved recommendations; and
monitors positions opened manually at the broker. It does not execute orders, scrape providers,
or auto-promote strategies or markets.
