# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-08T17:19:43.476927+00:00
- Score: 0.1429 | Grade: 미흡 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | False | 0.25 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'accept_request' has 72 NLOC exceeding the limit. |
| Maintainability.MainLoopComplexity | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'accept_request' has a cyclomatic complexity of 24 exceeding the limit. |
| Reliability.FaultTolerance.ResourceLoading | True | 0.2 |  |  | No warnings found in resource loading checks. |
| FunctionalSuitability.HttpBasic | False | 0.4 | SYSTEM_DEFECT | TARGET_SYSTEM | Will be evaluated by pytest execution output |
| TestExecution.PytestRun | False | 0.0 | SYSTEM_DEFECT | TARGET_SYSTEM | {'exit_code': 1} |
| FunctionalSuitability.HttpBasic | False | 0.4 | SYSTEM_DEFECT | TARGET_SYSTEM | {'passed': 0, 'failed': 1, 'skipped': 0} |