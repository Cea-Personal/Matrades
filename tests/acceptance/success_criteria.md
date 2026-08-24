# Success-Criteria Evidence Map

| Criterion | Executable evidence | CI artifact |
|---|---|---|
| SC-001 | `tests/contract/test_risk_api.py`, snapshot validation | Python test report |
| SC-002 | `tests/contract/test_risk_api.py`, `tests/e2e/test_release_risk_controls.py` | Python test report |
| SC-003 | `tests/contract/test_hil2_contract.py`, `tests/contract/test_hil3_contract.py`, `tests/security/test_no_broker_writes.py` | Security test report |
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
