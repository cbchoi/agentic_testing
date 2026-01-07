# quality_standards.py

# ISO/IEC 25010 국제 표준 및 사용자 정의 검증 지표 통합본
CUSTOM_QUALITY_SPEC = {
    "1. 기능 적합성 (Functional Suitability)": {
        "표준 준수": "ISO/IEC 25010 - 시스템이 명시된 요구사항을 얼마나 충족하는가",
        "기능 정확성 및 상태 전이 검증": """
            기준: 시스템의 핵심 상태(시작, 진행, 일시정지, 종료) 간의 전이가 트리거 발생 시 즉각적이고 정확하게 일어나는가?
            에이전트 행동 지침:
            1) 대상 게임에서 '게임 종료(Game Over)' 또는 '레벨 클리어'를 결정하는 조건 변수(예: hp, lives, score)를 찾아라.
            2) 'write_file'을 사용하여 해당 조건이 만족되는 시점에 검증용 로그(print문)를 삽입하라.
            3) 'execute_script'로 코드를 실행하여, 조건 발생 시 로그가 정상 출력되고 화면/상태가 전환되는지 증명하라.
        """
    },
    "2. 신뢰성 (Reliability)": {
        "표준 준수": "ISO/IEC 25010 - 특정 조건에서 시스템이 실패 없이 기능을 수행하는 정도",
        "결함 허용성 증명": """
            기준: 비정상적인 데이터나 환경에서도 시스템이 Crash 없이 안전하게 복구되는가?
            에이전트 행동 지침:
            1) 리소스 경로(이미지/사운드)를 의도적으로 틀리게 수정하거나 유효하지 않은 입력값을 주입하라.
            2) 시스템이 'try-except'를 통해 에러를 포착하고 사용자에게 안내 후 안전하게 종료되는지 코드로 증명하라.
        """
    },
    "3. 성능 효율성 (Performance Efficiency)": {
        "표준 준수": "ISO/IEC 25010 - 자원 사용량 대비 제공되는 성능의 정도",
        "시간 반응성 검증": """
            기준: 프레임 레이트(FPS)가 목표치(예: 60 FPS)를 안정적으로 유지하는가?
            에이전트 행동 지침:
            1) 메인 루프에 루프 실행 시간을 측정하는 코드를 삽입하여 프레임 간 지연 시간을 계산하라.
            2) 특정 부하 상황에서 지연 시간 변화를 데이터로 제시하라.
        """
    },
    "4. 유지보수성 (Maintainability)": {
        "표준 준수": "ISO/IEC 25010 - 제품이 수정, 개선, 교정되기 쉬운 정도",
        "모듈성 및 테스트 용이성": """
        기준: 함수 하나가 너무 많은 일을 하지 않고( < 50줄), 외부 의존성이 낮아 독립 실행이 가능한가?
        에이전트 행동 지침:
        1) 가장 복잡한 함수를 찾아 라인 수와 복잡도를 측정하라. (50줄 초과 시 결함으로 간주)
        2) 해당 함수가 속한 클래스나 모듈의 '순환 복잡도'가 10을 넘는지 판단하라.
        3) 해당 함수만 별도로 떼어내어 'execute_script'로 실행했을 때 독립적으로 작동하는지 확인하라.
        """
    }
}

def get_quality_prompt(project_type="game"):
    # 1. 수치 기준 설정
    standards = {
        "game": {"fps_min": 30, "loc_limit": 50, "complexity_limit": 15},
        "web_api": {"response_time_ms": 500, "loc_limit": 30, "complexity_limit": 10}
    }
    selected = standards.get(project_type, standards["game"])
    
    # 2. CUSTOM_QUALITY_SPEC 내용을 텍스트로 변환
    spec_text = ""
    for category, content in CUSTOM_QUALITY_SPEC.items():
        spec_text += f"\n[{category}]\n"
        for key, value in content.items():
            spec_text += f"- {key}: {value}\n"

    # 3. 최종 프롬프트 결합
    return f"""
    당신은 {project_type} 프로젝트의 품질 인증 심사원입니다. 
    아래의 [국제 표준 및 행동 지침]과 [수치 기준]을 결합하여 분석을 수행하십시오.

    [1. 수치 판정 절대 기준]
    - 성능: 측정값이 {selected.get('fps_min', selected.get('response_time_ms'))} 이상(또는 이하)일 것.
    - 유지보수성: 함수의 실질 코드 라인수가 {selected['loc_limit']}줄 이하일 것.
    - 코드 복잡도: 순환 복잡도 지수가 {selected['complexity_limit']} 이하일 것.

    [2. 상세 행동 지침 및 검증 항목]{spec_text}

    판정 시 실제 측정값(n)을 기준치와 비교하여 'Pass' 또는 'Fail'을 부여하고, 
    반드시 '데이터 근거' 섹션에 측정된 수치나 발견된 코드 라인을 명시하십시오.
    """