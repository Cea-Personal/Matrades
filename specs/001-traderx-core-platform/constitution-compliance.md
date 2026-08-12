# Constitution compliance check

Status: **PASS for the implemented code and test suite**.

- Manual execution boundary: provider, API, worker, and source guards expose no live-order action.
- Three-category selection: eligibility precedes ranking and activation/replacement is explicit.
- Safety authority: server-side Risk Manager may reduce or block a recommendation; missing critical
  data fails closed; capacity never exceeds two positions.
- Evidence governance: strategies, validation, paper approval, journal, and market history use
  immutable or append-only evidence models; reactivation ends in human approval.
- Operations: secrets are encrypted and redacted; integration capabilities are allowlisted; audit,
  jobs, health, and notification paths are available from the UI contract.

This is a software release-gate result, not authorization to deploy or place trades. Production
deployment requires the runbook rehearsal and owner approval.
