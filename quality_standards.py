from typing import Dict, Any

class ISO25010Standard:
    """
    ISO/IEC 25010 Quality Model - Structural Schema
    시스템의 범용적 패턴 분석과 변수 추적 로직을 포함합니다.
    """
    def __init__(self):
        self.standard_id = "ISO/IEC 25010"
        
        # [1] Taxonomy: 지표의 정의
        self.taxonomy = {
            "FunctionalSuitability": {
                "FunctionalCorrectness": "Precision and accuracy of logical results",
                "StateTransitionValidation": "Correctness of state triggers (Menu/Game/Pause/Exit)"
            },
            "Reliability": {
                "FaultTolerance": "Implementation of exception handling (try-except)",
                "Recoverability": "State restoration capability after failure"
            },
            "PerformanceEfficiency": {
                "TimeBehaviour": "Stability and appropriateness of execution timing (FPS)",
                "ResourceUtilization": "Efficiency of CPU/Memory consumption"
            },
            "Maintainability": {
                "Modularity": "Independence of components (LOC <= 50)",
                "Analysability": "Cyclomatic complexity and code readability",
                "Testability": "Ease of performing independent unit tests"
            }
        }

        # Execution-ready spec: machine-readable rules and measurement methods.
        # This is the single source of truth. Human-readable reports must be derived from this structure.
        self.exec_spec = {
            "domain": "game",
            "checks": [
                {
                    "id": "Maintainability.FunctionLOC",
                    "metric": "max(function_loc)",
                    "method": "AST: end_lineno - lineno + 1 per FunctionDef",
                    "rule": "function_loc <= {loc_limit} for all functions",
                    "weight": 0.25,
                },
                {
                    "id": "Maintainability.MainLoopComplexity",
                    "metric": "top_level_while(branch_count, nesting_depth, cyclomatic_proxy)",
                    "method": "AST: analyze largest top-level While node",
                    "rule": "branch_count<=25 AND nesting_depth<=4 AND cyclomatic_proxy<=20",
                    "weight": 0.15,
                },
                {
                    "id": "PerformanceEfficiency.TimeBehaviour",
                    "metric": "min(resolved_fps)",
                    "method": "AST: resolve clock.tick(arg) where arg is constant or traced assignment",
                    "rule": "resolved_fps >= {fps_min}",
                    "weight": 0.25,
                },
                {
                    "id": "Reliability.FaultTolerance.ResourceLoading",
                    "metric": "unprotected_resource_calls",
                    "method": "AST: detect pygame.image.load / pygame.mixer.Sound / open(...) and check try scope",
                    "rule": "all resource loading calls must be within try/except",
                    "weight": 0.15,
                },
                {
                    "id": "FunctionalSuitability.StateTransitionValidation.ExitSignals",
                    "metric": "exit_signal_patterns",
                    "method": "Text scan: pygame.QUIT, sys.exit, running=False, quit()",
                    "rule": "at least one exit signal exists",
                    "weight": 0.20,
                },
            ],
            "grading": {
                "grade_thresholds": {"우수": 0.85, "보통": 0.70, "미흡": 0.0},
                "score_method": "weighted_pass_ratio",
            },
        }

    def get_thresholds(self, domain: str = "game") -> Dict[str, Any]:
        return {
            "game": {"fps_min": 30, "loc_limit": 50, "complexity_limit": 15},
            "web_api": {"response_time_ms": 500, "loc_limit": 30, "complexity_limit": 10},
            "c_http_server": {"loc_limit": 80, "complexity_limit": 20, "cppcheck_max_warnings": 0},
        }.get(domain, {"fps_min": 30, "loc_limit": 50, "complexity_limit": 15})

# 글로벌 인스턴스 생성
iso_spec = ISO25010Standard()

def get_quality_prompt(project_type="game"):
    selected = iso_spec.get_thresholds(project_type)
    
    return (
        "You are a QA inspection executor. Do not invent judgments.\n"
        "Output MUST be JSON only. No markdown.\n"
        "Follow the execution spec and fill measured values + evidence.\n"
        f"Thresholds: loc_limit={selected['loc_limit']}, fps_min={selected.get('fps_min')}\n"
        f"Taxonomy: {iso_spec.taxonomy}\n"
        f"ExecSpec: {iso_spec.exec_spec}\n"
    )


def get_quality_spec(project_type: str = "game") -> Dict[str, Any]:
    selected = iso_spec.get_thresholds(project_type)

    if project_type == "c_http_server":
        return {
            "domain": "c_http_server",
            "thresholds": selected,
            "checks": [
                {
                    "id": "Maintainability.FunctionLOC",
                    "metric": "max(function_nloc)",
                    "method": "LIZARD: parse function NLOC from lizard output",
                    "rule": "function_nloc <= {loc_limit} for all functions",
                    "weight": 0.25,
                },
                {
                    "id": "Maintainability.MainLoopComplexity",
                    "metric": "max(function_ccn)",
                    "method": "LIZARD: parse CCN from lizard output",
                    "rule": "function_ccn <= {complexity_limit} for all functions",
                    "weight": 0.15,
                },
                {
                    "id": "Reliability.FaultTolerance.ResourceLoading",
                    "metric": "cppcheck_warning_count",
                    "method": "CPPCHECK: count warnings in stderr/stdout",
                    "rule": "cppcheck_warning_count <= {cppcheck_max_warnings}",
                    "weight": 0.20,
                },
                {
                    "id": "FunctionalSuitability.HttpBasic",
                    "metric": "pytest_passed_failed",
                    "method": "PYTEST: parse passed/failed from pytest output",
                    "rule": "failed == 0 AND passed >= 1",
                    "weight": 0.40,
                },
            ],
        }

    # default: game
    spec = dict(iso_spec.exec_spec)
    spec["domain"] = "game"
    spec["thresholds"] = selected
    return spec
