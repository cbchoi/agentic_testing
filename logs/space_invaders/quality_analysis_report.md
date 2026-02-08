# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-08T16:29:59.248278+00:00
- Score: 0.85 | Grade: 우수 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | True | 0.25 |  |  | 최대 LOC는 36으로, 50 이하입니다. |
| Maintainability.MainLoopComplexity | True | 0.15 |  |  | branch_count는 10, nesting_depth는 3, cyclomatic_proxy는 15로 기준을 만족합니다. |
| PerformanceEfficiency.TimeBehaviour | True | 0.25 |  |  | resolved_fps는 60으로, 30 이상입니다. |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | 리소스 로딩 호출 중 2개가 try/except 내부가 아닙니다. |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | True | 0.2 |  |  | exit signal 패턴으로 pygame.QUIT와 sys.exit가 발견되었습니다. |
| TestExecution.PytestRun | True | 0.0 |  |  | {'exit_code': 0} |