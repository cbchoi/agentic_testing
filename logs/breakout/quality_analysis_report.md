# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-08T16:21:32.438198+00:00
- Score: 0.85 | Grade: 우수 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | True | 0.25 |  |  | Function Ball.__init__ has a loc of 50. |
| Maintainability.MainLoopComplexity | True | 0.15 |  |  | Main loop in main.py has 16 branches, depth of 4, and cyclomatic complexity of 12. |
| PerformanceEfficiency.TimeBehaviour | True | 0.25 |  |  | Resolved FPS is 60 from clock.tick(FPS). |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | 6 resource loading calls found outside of try/except. |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | True | 0.2 |  |  | Found exit signal: pygame.QUIT in main.py. |
| TestExecution.PytestRun | False | 0.0 | SYSTEM_DEFECT | TARGET_SYSTEM | {'exit_code': 1} |