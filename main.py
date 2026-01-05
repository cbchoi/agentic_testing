import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
# GitCloneTool 임포트 추가
from tools.file_tools import ReadFileTool, WriteFileTool, ExecuteScriptTool, GitCloneTool
from quality_standards import get_quality_prompt

# 1. 환경변수 로드
load_dotenv()

# 2. 에이전트 정의 
analyzer = Agent(
    role='ISO/IEC 25010 품질 인증 심사원',
    goal=f'SolarWolf 프로젝트가 다음의 고정 품질 표준을 만족하는지 실제 코드로 증명하라: {get_quality_prompt()}',
    backstory="""너는 소프트웨어 품질 국제 표준인 ISO/IEC 25010의 전문가야. 
    단순히 코드를 읽는 것에 그치지 말고, 제공된 명세서의 '행동 지침'에 따라 
    직접 로그를 심거나(write_file) 실행하여(execute_script) 품질을 수치로 증명해야 해. 
    보고서는 반드시 한국어로 작성하며, Pass/Fail 여부를 명확히 판정하라.""",
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ReadFileTool()],
    # 일관성 확보
    config={
        "temperature": 0.0, 
    }
)

# # 3. 분석할 타겟 깃허브 주소 (원하는 주소로 변경 가능) --> 직접 클론중.
# target_repo_url = "https://github.com/pygame/solarwolf"

# 4. 분석 작업 정의
github_analysis_task = Task(
    description=f"""
    [지침: 소스코드는 이미 'target_apps/cloned_app'에 준비되어 있다]
    [재현성 보장: 매 실행마다 동일한 수치를 도출하기 위해 아래 상세 검색 지침을 따르라]
    
    1. 분석 대상 파일 집중 분석:
       - 'target_apps/cloned_app/solarwolf/game.py'
       - 'target_apps/cloned_app/solarwolf/main.py'
    
    2. [필수 데이터 수집 - 누락 금지]
       - **FPS 수치**: 'main.py' 파일 내에서 `clock.tick(` 문자열을 찾아 그 인자값(예: 40 또는 60)을 정확히 기록하라. 이는 '성능 효율성'의 근거가 된다.
       - **함수 라인 수(LOC)**: 'main.py'의 `gamemain` 함수와 `main` 함수의 시작(def)부터 끝까지 줄 번호를 세어 기록하라.
       - **순환 복잡도**: 위 함수들 내부의 if, while, for, and, or 키워드 개수를 세어 복잡도 수치를 추정하라.
    
    3. [논리적 증명 및 코드 추적]
       - **상태 전이**: 'game.py'에서 `lives` 변수가 선언된 위치와, 값이 감소하거나 0인지 체크하는 로직이 있는 파일/줄 번호를 찾아 명시하라.
       - **신뢰성**: 'main.py' 상단의 try-except 블록이 어떤 예외(예: KeyboardInterrupt)를 처리하는지 줄 번호와 함께 기록하라.
    
    4. [리포트 작성 규칙]
       - {get_quality_prompt()} 지침을 100% 적용하라.
       - 결과는 반드시 아래의 **범용 품질 평가 표** 형식을 유지하며 'quality_analysis_report.md'에 저장하라.

    | 품질 특성 | 검증 항목 (대상 변수/함수/줄번호) | 판정 | 근거 요약 및 수치 데이터 |
    |-----------|----------------------------------|------|--------------------------|
    | 기능 적합성 | 핵심 상태 전이 트리거 (예: 종료/승리 조건) | | |
    | 신뢰성 | 예외 처리 및 방어 코드 (try-except 등) | | |
    | 성능 효율성 | 자원 제어 및 반응성 지표 (FPS/반복주기 등) | | |
    | 유지보수성 | 모듈 독립성 및 코드 복잡도 (LOC/복잡도) | | |
    """,
    expected_output="수치와 줄 번호가 포함된 표 형식의 ISO 25010 기반 상세 품질 보고서",
    agent=analyzer,
    output_file='quality_analysis_report.md'
)

# 5. 크루 설정 및 실행
qa_crew = Crew(
    agents=[analyzer],
    tasks=[github_analysis_task],
    process=Process.sequential
)

if __name__ == "__main__":
    print(f"### [GPT-4o-mini] 깃허브 기반 품질 분석 시작 ###")
    try:
        result = qa_crew.kickoff()
        print(f"\n\n### 분석 완료! 보고서 확인: quality_analysis_report.md")
    except Exception as e:
        print(f"\n에러 발생: {e}")