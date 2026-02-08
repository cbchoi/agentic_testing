# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-04T18:24:11.638391+00:00
- Score: 0.85 | Grade: 우수 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | True | 0.25 |  |  | Max LOC of functions in flappy.py is 40. |
| Maintainability.MainLoopComplexity | True | 0.15 |  |  | The main loop in flappy.py has 10 branches, depth of 3, and cyclomatic complexity of 12. |
| PerformanceEfficiency.TimeBehaviour | True | 0.25 |  |  | The FPS is set to 30 in the GameConfig class. |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | There are 2 resource loading calls that are not protected by try/except. |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | True | 0.2 |  |  | Exit signals are implemented in the check_quit_event method. |
| TestExecution.PytestRun | False | 0.0 | SYSTEM_DEFECT | TARGET_SYSTEM | {'exit_code': 1} |