# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-04T18:35:15.770184+00:00
- Score: 0.85 | Grade: 우수 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | True | 0.25 |  |  | Maximum function LOC is within the limit. |
| Maintainability.MainLoopComplexity | True | 0.15 |  |  | Complexity measures are within the specified limits. |
| PerformanceEfficiency.TimeBehaviour | True | 0.25 |  |  | Minimum resolved FPS is above the threshold. |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | Two resource loading calls were detected outside try/except. |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | True | 0.2 |  |  | Exit signals were detected in the code. |
| TestExecution.PytestRun | False | 0.0 | ENVIRONMENT_DEPENDENCY_MISSING | EXECUTION_ENVIRONMENT | {'exit_code': 1} |