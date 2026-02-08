# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-02-08T16:04:49.277080+00:00
- Score: 0.85 | Grade: 우수 | OverallPass: False

## Checks
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | True | 0.25 |  |  | Max LOC found in src/entities/player.py, function __init__ is 38. |
| Maintainability.MainLoopComplexity | True | 0.15 |  |  | Main loop in src/flappy.py shows a complexity count of 12 branches, 3 nesting depth, and 11 cyclomatic complexity. |
| PerformanceEfficiency.TimeBehaviour | True | 0.25 |  |  | Resolved FPS of 30 from src/flappy.py where self.config.fps is assigned to 30. |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | Found 1 unprotected resource loading call in src/utils/sounds.py:__init__. |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | True | 0.2 |  |  | Found exit signals including pygame.quit() and sys.exit() in src/flappy.py. |
| TestExecution.PytestRun | True | 0.0 |  |  | {'exit_code': 0} |