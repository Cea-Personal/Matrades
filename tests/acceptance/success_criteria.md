# Success-Criteria Evidence Map

| Criterion | Executable evidence | CI artifact |
|---|---|---|
| SC-001 | `tests/contract/test_risk_api.py`, snapshot validation | Python test report |
| SC-002 | `tests/contract/test_risk_api.py`, `tests/e2e/test_release_risk_controls.py` | Python test report |
| SC-003 | `tests/contract/test_trade_plan_execution_api.py`, `tests/security/test_no_execution_bypass.py` | Security test report |
| SC-004 | `tests/property/test_risk_invariants.py`, reservation concurrency | Property/integration report |
| SC-005 | `tests/e2e/test_safe_trade_decision.py` | E2E report/screenshots |
| SC-006 | `tests/integration/test_strategy_validation.py` | Strategy validation report |
| SC-007 | `tests/e2e/test_strategy_lifecycle.py` plus moderated usability evidence | Release usability artifact |
| SC-008 | `tests/property/test_strategy_invariants.py`, similarity replay | Python test report |
| SC-009 | `tests/e2e/test_release_agent_configuration.py` | Agent runtime report |
| SC-010 | `tests/security/test_credential_vault.py`, redaction tests | Security report |
| SC-011 | `tests/failure/test_knowledge_degradation.py` | Failure report |
| SC-012 | daily research replay and `tests/integration/test_performance_slos.py` | Performance report |
| SC-013 | `tests/integration/test_performance_slos.py` | Performance report |
| SC-014 | `tests/contract/test_journal_reconstruction.py` | Audit reconstruction report |
| SC-015 | `tests/e2e/test_review_and_performance.py` plus moderated usability evidence | Release usability artifact |

SC-007 and SC-015 require representative-user study results in addition to executable UI coverage; code-level gates cannot manufacture human-study percentages.

```yaml
autonomous_evidence:
  SC-001: tests/contract/test_trade_plan_execution_api.py
  SC-002: tests/property/test_autonomous_risk_invariants.py
  SC-003: tests/security/test_no_execution_bypass.py
  SC-004: tests/integration/test_trade_plan_reservation_concurrency.py
  SC-005: tests/e2e/test_safe_automated_trade.py
  SC-006: tests/integration/test_strategy_autonomous_validation.py
  SC-007: tests/e2e/test_strategy_origins.py
  SC-008: tests/security/test_strategy_activation_boundaries.py
  SC-009: tests/integration/test_agent_runtime.py
  SC-010: tests/security/test_configuration_security.py
  SC-011: tests/failure/test_knowledge_degradation.py
  SC-012: tests/integration/test_autonomous_research_slos.py
  SC-013: tests/integration/test_autonomous_platform_slos.py
  SC-014: tests/contract/test_live_journal_contract.py
  SC-015: tests/e2e/test_review_and_performance.py
  SC-016: tests/integration/test_mt5_execution_bridge.py
  SC-017: tests/security/test_execution_command_security.py
  SC-018: tests/e2e/test_live_trade_workspace.py
  SC-019: tests/security/test_autonomous_platform_threats.py
  SC-020: tests/contract/test_openapi_autonomous_consistency.py
  SC-021: tests/contract/test_autonomous_event_idempotency.py
  SC-022: tests/failure/test_autonomous_safe_failure_matrix.py
  SC-023: tests/contract/test_agent_registry.py
  SC-024: tests/e2e/test_knowledge_assistant.py
```
