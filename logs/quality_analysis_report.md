# Quality Analysis (Derived from logs/result.json)
- GeneratedAt: 2026-01-27T16:23:38.663613+00:00
- Score: 0.0 | Grade: 미흡 | OverallPass: False

## Checks
| Check ID | Pass | Weight | Evidence |
|---|---:|---:|---|
| Maintainability.FunctionLOC | False | 0.25 | file=main.py; func=main_loop; evidence=total lines 70 |
| Maintainability.MainLoopComplexity | False | 0.15 | file=main.py; evidence=while loop complexity exceeded limits |
| PerformanceEfficiency.TimeBehaviour | False | 0.25 | file=main.py; evidence=clock.tick(25) |
| Reliability.FaultTolerance.ResourceLoading | False | 0.15 | file=main.py; evidence=pygame.image.load without try-except |
| FunctionalSuitability.StateTransitionValidation.ExitSignals | False | 0.2 | file=main.py; evidence=no exit signals found |