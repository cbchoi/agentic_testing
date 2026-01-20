from typing import Dict, List, Any

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

        # [2] Principles: 범용적 행동 지침
        self.agent_principles = {
            "StateTransitionValidation": [
                "Identify event triggers (e.g., QUIT, KEYDOWN, MOUSEBUTTON) rather than specific names.",
                "Trace flow between application states via conditional branch analysis."
            ],
            "FaultTolerance": [
                "Locate 'try-except' blocks at I/O and resource loading points.",
                "Verify if error handling prevents total system crash."
            ],
            "TimeBehaviour": [
                "Locate timing control mechanisms (e.g., clock.tick, time.sleep).",
                "CRITICAL: If an argument is a variable (e.g., fps), trace back to find its assigned numeric value."
            ],
            "Maintainability": [
                "Measure real LOC for all functions and check if they exceed the limit.",
                "Calculate Cyclomatic Complexity by counting control flow keywords (if, for, while, try)."
            ]
        }

    def get_thresholds(self, domain: str = "game") -> Dict[str, Any]:
        return {
            "game": {"fps_min": 30, "loc_limit": 50, "complexity_limit": 15},
            "web_api": {"response_time_ms": 500, "loc_limit": 30, "complexity_limit": 10}
        }.get(domain, {"fps_min": 30, "loc_limit": 50, "complexity_limit": 15})

# 글로벌 인스턴스 생성
iso_spec = ISO25010Standard()

def get_quality_prompt(project_type="game"):
    selected = iso_spec.get_thresholds(project_type)
    
    return f"""
    당신은 {iso_spec.standard_id} 표준을 준수하는 전문 기술 심사원입니다.
    대상 코드가 무엇이든 보편적으로 적용 가능한 '기능적 패턴'을 추출하십시오.

    [범용 분석 지침]
    1. 특정 변수명에 의존하지 말고 {iso_spec.agent_principles}에 정의된 행동 원칙을 따르십시오.
    2. 특히 성능 분석 시, clock.tick(fps) 처럼 변수가 사용된 경우 해당 변수의 정의부(fps=60)를 반드시 역추적하여 실제 수치를 확인하십시오.
    3. 테스트 코드 생성 시 'import sys, os' 등 필요한 모듈 누락으로 인한 NameError가 발생하지 않도록 주의하십시오.

    [품질 분류 체계 (Taxonomy)]
    {iso_spec.taxonomy}

    [판단 임계치 (Thresholds)]
    - 함수당 라인 수(LOC): {selected['loc_limit']}줄 이하
    - 순환 복잡도(Complexity): {selected['complexity_limit']} 이하
    - 성능 지표: 최소 {selected.get('fps_min')} FPS 기준

    [보고서 작성 규칙]
    1. 결과 스키마: [Characteristic].[SubCharacteristic] | 판정(Pass/Fail) | 데이터 근거(수치 및 위치)
    2. 모든 분석 설명은 한국어로 작성하되, Key값은 영문 Taxonomy를 유지하십시오.
    """