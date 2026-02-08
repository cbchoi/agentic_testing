# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-08T16:54:36.654191+00:00
- Score: 0.4286 | Grade: 미흡 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | False | 0.25 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'make_safe_url_old' has NLOC of 60, 'init_sockin' has NLOC of 77, 'parse_commandline' has NLOC of 167 which is greater than 80. |
| Maintainability.MainLoopComplexity | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'parse_commandline' has CCN of 65, 'init_sockin' has CCN of 26 which is greater than 20. |
| Reliability.FaultTolerance.ResourceLoading | True | 0.2 |  |  | No resource loading calls detected in current analysis. |
| FunctionalSuitability.HttpBasic | False | 0.4 | SYSTEM_DEFECT | TARGET_SYSTEM | Will be evaluated by pytest execution output. |
| TestExecution.PytestRun | True | 0.0 |  |  | {'exit_code': 0} |
| FunctionalSuitability.HttpBasic | True | 0.4 |  |  | {'passed': 1, 'failed': 0, 'skipped': 0} |