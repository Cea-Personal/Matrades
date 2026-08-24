# Matrades V1 Validation Report

Date: 2026-08-24

## Automated evidence

The repository implements and exercises the quickstart’s safety paths with deterministic fixtures: secure configuration primitives, current-equity risk decisions, independent prompt resolution, Codex-default registry, same-runtime fallback, research ranking/HIL-1, equal-origin strategy validation, HIL-2 manual-entry intent, read-only MT5 reconciliation, HIL-3 intent, knowledge authority isolation, journal reconstruction, and performance attribution.

Local Python evidence at implementation time: all implemented unit, contract, property, integration, replay, security, failure, acceptance-support, and source-level UI tests passed. Exact command/output belongs in the CI test artifact for the release commit.

## Stop-condition assessment

- No V1 broker-write method or endpoint exists; a repository-wide assertion enforces this.
- Missing/stale or mismatched authoritative facts block or degrade affected action.
- `CODEX_APP_SERVER` is the default for all 15 protected agents. LiteLLM is optional and explicit; fallbacks cannot cross runtimes.
- Prompt inheritance resolves system and user chains independently; tools are separately versioned.
- Current equity, reserved stop risk, strictest limits, correlation groups, and dynamic capacity feed pre-trade decisions.
- Knowledge is context-only and owner-scoped.
- Strategy origins share compiler, validation, paper, and promotion gates.

## Environment-dependent validation still required per deployment

Before production release, run Compose against real PostgreSQL 17/TimescaleDB/pgvector and Redis, execute migration upgrade/downgrade on a disposable clone, exercise configured provider sandboxes, connect a demo read-only MT5 bridge, validate Codex App Server supervision, and run real Playwright journeys. Record dependency/container/secret scanner outputs and complete representative-user studies for SC-007 and SC-015. These are deployment/research evidence gates, not claims that can be satisfied by fixtures alone.
