# Contract compatibility report

The FastAPI application registers every documented `/api/v1` resource family and its OpenAPI
contract tests assert that accounts, markets, strategies, paper approvals, opportunities,
positions, journal, rotation, and operations routes are present. Domain events use a
CloudEvents-compatible outbox envelope; provider ports intentionally omit order-submission
methods. The generated web client remains a minimal typed boundary until the OpenAPI generator is
introduced in CI.

Compatibility status: **compatible with implemented V1 read/research/decision-support scope**.
There is intentionally no real-money order operation in the HTTP, worker, or provider contracts.
