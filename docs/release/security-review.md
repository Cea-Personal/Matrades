# Security and Supply-Chain Review

Release checks cover locked Python/npm dependencies, dependency vulnerability and license review, container scanning, secret scanning, static authorization tests, read-only broker assertions, and build provenance. CI must archive machine-readable results.

Approved development-only exceptions:

- `.env.example` contains a clearly labeled non-production placeholder and no credential.
- The optional LiteLLM image uses an upstream tag in local Compose; production deployment must pin an approved digest.
- Local blob storage is for development only; production requires encrypted, access-controlled object storage.

No exception permits broker writes, secret logging, automatic cross-runtime fallback, stale-fact action, or bypass of MFA/step-up controls.
