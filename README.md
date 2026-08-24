# Matrades

Matrades is Codex-first, human-in-the-loop multi-market trading decision support. It researches Forex, metals, and crypto; validates strategies; computes equity-aware risk; and reconciles manually entered MT5 trades. V1 contains no broker-write capability.

## Local setup

Requirements: Python 3.13 with `uv`, Node 24/npm 11, Docker Compose. Copy `.env.example` to `.env` and replace development secrets with test-only values.

```bash
make bootstrap
docker compose -f infra/compose/compose.yaml up --build postgres redis api worker agent-worker web
make migrate
make seed
make test
```

LiteLLM is optional and never a fallback from Codex:

```bash
docker compose -f infra/compose/compose.yaml --profile litellm up litellm
```

After connecting it, explicitly create a LiteLLM-bound model profile and assign individual agents. Unassigned agents remain on Codex App Server.

API docs are at `http://localhost:8000/docs`; the web UI is at `http://localhost:3000`. Use fixture/test credentials only. MT5 setup requires the read-only bridge and a demo account. For troubleshooting, inspect `/api/v1/operations/health`: stale authoritative inputs intentionally cause BLOCK, WAIT, DEGRADED, or NO TRADE.

## Authentication

Open `http://localhost:3000/auth` and select **Sign up**. In development, the UI displays the generated email-verification token; production deployments must deliver that token through the configured notification provider. After verification, scan or enter the TOTP secret, save the one-time recovery codes, and confirm a current six-digit code. The server then creates an eight-hour HttpOnly session cookie.

Every later login requires the password plus TOTP or an unused recovery code. **Forgot password?** starts the recovery flow; completing it revokes every existing session. Sensitive credential changes also require a recent MFA step-up from Configuration → Security. Authentication and owner identity come exclusively from the server session—not request headers or browser-supplied owner IDs.
