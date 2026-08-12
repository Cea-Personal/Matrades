# Requirements traceability

The 94 functional requirements are implemented and evidenced by the nine story groups in
`tasks.md`: FR-001–FR-012 (identity/account/risk) map to T037–T059; FR-013–FR-024 (market
selection) to T060–T081; FR-025–FR-038 (strategy/validation) to T082–T112; FR-039–FR-047
(paper/approval) to T113–T129; FR-048–FR-057 (recommendations) to T130–T148; FR-058–FR-066
(manual monitoring) to T149–T166; FR-067–FR-073 (journal) to T167–T180; FR-074–FR-080 (rotation)
to T181–T193; and FR-081–FR-094 (operations) to T194–T218.

The 18 success criteria are covered by Phase 12 tests T219–T226, with risk latency specifically
checked in `tests/performance/test_success_criteria.py`. Each cited task is checked only after its
focused test checkpoint passes.
