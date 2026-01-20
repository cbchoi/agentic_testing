import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool, RunPytestTool
from quality_standards import get_quality_prompt, iso_spec

load_dotenv()

TARGET_DIR = "target_apps/cloned_app"
TEST_FILE_REL = "test_quality_check.py"
TEST_FILE_ABS = os.path.join(TARGET_DIR, TEST_FILE_REL)

# ----------------------------------------------------------------
# 1. Agents 설정: 페르소나와 전문성 강화
# ----------------------------------------------------------------

analyzer = Agent(
    role="ISO/IEC 25010 품질 인증 심사원",
    goal=f"pygame 프로젝트 소스코드를 정밀 분석하여 품질 표준 만족 여부를 증명하라: {get_quality_prompt()}",
    backstory=(
        "너는 소프트웨어 품질 국제 표준 전문가야. 주관적인 판단을 배제하고 오직 코드 데이터로만 말한다.\n"
        "독해를 통해 함수의 라인 수, 복잡도, 예외 처리 위치를 정확히 찾아내며,\n"
        "특히 변수(예: fps)가 사용된 경우 해당 변수의 실제 할당값을 역추적하여 수치화한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ListFilesTool(), ReadFileTool()],
    config={"temperature": 0.0},
)

test_creator = Agent(
    role="Pytest 기반 테스트 코드 생성 전문가",
    goal="분석 리포트를 바탕으로 '변수 추적'이 가능하고 문법적으로 완벽한 테스트 코드를 작성하라.",
    backstory=(
        "너는 파이썬 문법 무결성에 결벽증이 있는 테스트 엔지니어다.\n"
        "특히 assert 문을 작성할 때 마지막에 불필요한 쉼표(,)를 남기는 실수를 절대 하지 않으며,\n"
        "파일 상단에 'import sys, os, pytest, re, pathlib'를 필수 포함하여 환경 독립성을 확보한다.\n"
        "동적으로 변하는 변수값을 텍스트 분석으로 찾아내는 정교한 정규식 테스트 코드를 짠다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ListFilesTool(), ReadFileTool(), WriteFileTool()],
    config={"temperature": 0.0},
)

test_reporter = Agent(
    role="테스트 자동화 및 결과 분석가",
    goal="작성된 테스트 코드를 실행하고, 그 결과를 바탕으로 최종 통합 품질 보고서를 작성하라.",
    backstory=(
        "너는 테스트 결과의 신뢰성을 책임진다. RunPytestTool의 실행 로그 원문을 훼손 없이 인용하며,\n"
        "테스트 실패 시 그것이 소스 코드의 결함인지, 테스트 코드의 문법 오류인지 명확히 판별하여 보고한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ReadFileTool(), RunPytestTool()],
    config={"temperature": 0.0},
)

# ----------------------------------------------------------------
# 2. Tasks 설정: 실행 순서와 제약 사항 명확화
# ----------------------------------------------------------------

github_analysis_task = Task(
    description=f"""
[0. 실행 순서]
1) ListFilesTool로 '{TARGET_DIR}' 폴더의 파일 목록 확보.
2) 핵심 로직 파일(최소 2개) 선정 후 ReadFileTool로 분석.

[1. 분석 포인트]
- {get_quality_prompt()} 지침 엄격 준수.
- 성능(FPS): 변수 역추적(Variable Tracing)을 통해 실제 정수값 도출.
- 유지보수성: 함수별 LOC 및 제어문 기반 복잡도 측정.

[2. 출력 형식 - 반드시 이 양식만 반복해서 사용할 것]
각 품질 특성마다 아래의 마크다운 형식을 개별적으로 작성하라.

### [품질 검증 명세서]
- 품질 특성: [ISO 표준 항목명]
- 검증 대상: [파일 경로 / 줄번호]
- 판정 규칙 (Decision Rule): [정량적 조건식]
- 측정 방식 (Measurement Method): [정적 분석 / AST / 패턴 탐색 등]
- 최종 판정: [Pass 또는 Fail]
- 데이터 근거: [실제 측정값과 임계치 비교 결과]

[출력 규칙]
1. 위 '### [품질 검증 명세서]' 블록을 분석한 항목의 개수만큼 반복해서 나열하라.
2. '1. 신뢰성' 처럼 임의로 번호를 매겨서 그룹화하지 마라.
3. 모든 내용은 한국어로 작성하라.
""",
    expected_output="규정된 양식을 반복 사용하여 작성된 개별 품질 검증 명세서 리스트",
    agent=analyzer,
    output_file="quality_analysis_report.md",
)

test_generation_task = Task(
    description=f"""
[1. 파일 생성 및 환경 고정]
- 출력 경로: '{TEST_FILE_ABS}'
- 필수 임포트: import pytest, import re, import os, import sys, ast, from pathlib import Path

[2. Fixture 선언 및 핵심 파일 선정]
- 반드시 아래 구조의 fixture를 파일 상단에 직접 구현하라:
  @pytest.fixture(scope="session")
  def core_files():
      project_root = Path(__file__).resolve().parent
      # 점수화 로직: 'pygame'을 임포트하고 게임 루프가 포함된 소스 파일(Top 1~3) 선별
      files = [str(p) for p in project_root.rglob("*.py") if "test_" not in p.name and "venv" not in str(p)]
      return files

[3. 수치 중심 정밀 검증 로직 (ISO/IEC 25010 준수)]
- **유지보수성(test_03)**: 파일 전체 라인 수 대신, `ast` 모듈을 사용하여 **'개별 함수(FunctionDef)'**의 실제 라인 수를 각각 측정하라.
  - 각 함수가 **{iso_spec.get_thresholds()['loc_limit']}줄**을 초과하는지 검사하고, 초과 시 어떤 함수가 몇 줄인지 에러 메시지에 명시하라.
- **성능(test_02)**: 변수 `fps`를 역추적하여 실제 할당값이 **{iso_spec.get_thresholds()['fps_min']} FPS** 이상인지 수치적으로 비교하라.
- **신뢰성(test_01)**: `try-except` 블록 또는 'KeyboardInterrupt' 처리 코드가 소스 파일 내에 존재하는지 정적 분석으로 검증하라.
- **기능(test_04)**: 'pygame.QUIT', 'sys.exit()', 'running = False' 등 종료 패턴 중 하나 이상이 존재하는지 확인하라.

[4. 문법 무결성 및 디버깅 정보]
- assert 문 작성 시 문법 오류를 원천 차단(쉼표 제거, 따옴표 쌍 확인)하라.
- 실패 시 f-string을 사용하여 구체적인 실측 수치와 임계치를 메시지로 출력하라.
""",
    expected_output=f"ast 모듈 기반 함수 단위 실측과 {iso_spec.get_thresholds()['loc_limit']}줄 기준이 적용된 고도화된 pytest 스크립트",
    agent=test_creator,
    context=[github_analysis_task],
)

test_execution_task = Task(
    description=f"""
[1. 실행 전 검증]
- ReadFileTool로 '{TEST_FILE_ABS}'를 읽어 5개의 테스트 함수가 문법 오류(끝에 쉼표 등) 없이 생성되었는지 검사하라.
- 오류 발견 시 test_creator에게 재작성을 요청하라.

[2. 실행]
- RunPytestTool을 실행 인자 '{TEST_FILE_REL} -q'로 호출하라. (CWD: {TARGET_DIR})
- 실행 로그(EXIT_CODE, STDOUT 등)를 확보하라.

[3. 최종 보고서 작성]
반드시 아래 형식을 한 글자도 빠짐없이 유지하여 'final_tc_report.md'를 작성하라:

--------------------------------------------------
# [최종 품질 통합 보고서]

## 1. 정적 분석 요약 (에이전트 1 결과)
- (품질 특성별 Pass/Fail 요약 및 핵심 결함 코드 인용)

## 2. 동적 테스트 결과 요약
- **직접 실행 상태:** (성공/실패 여부)
- **테스트 성공 개수:** (숫자) / **실패 개수:** (숫자)
- **검증 범위:** (변수 추적, LOC 실측, 예외 처리 확인 등)

## 3. pytest 실행 증명 로그 (원문)
- (RunPytestTool 결과 원문 전체 포함)

## 4. 상세 실패 원인 및 기술 분석
- (실패 시 Traceback 분석 및 결함 위치 파악)

## 5. 종합 판정 및 개선 권고
- **최종 품질 등급:** (우수/보통/미흡)
- **종합 판정:** (Pass / Fail)
- **판정 근거:** (정적/동적 분석 결과의 종합 결론)
- **우선 개선 권고 사항:** (가장 시급한 수정 사항 1~2개)
--------------------------------------------------
""",
    expected_output="[최종 품질 통합 보고서] 형식을 완벽히 준수한 최종 보고서",
    agent=test_reporter,
    context=[github_analysis_task, test_generation_task],
    output_file="final_tc_report.md",
)

# ----------------------------------------------------------------
# 3. Crew & Execution
# ----------------------------------------------------------------

qa_crew = Crew(
    agents=[analyzer, test_creator, test_reporter],
    tasks=[github_analysis_task, test_generation_task, test_execution_task],
    process=Process.sequential,
)

if __name__ == "__main__":
    print("### [AI QA Team] 품질 분석 및 자동화 테스트 시작 ###")
    try:
        qa_crew.kickoff()
        print("\n### 작업 완료!")
        print("- 분석 결과: quality_analysis_report.md")
        print("- 최종 리포트: final_tc_report.md")
    except Exception as e:
        print(f"\n시스템 에러 발생: {e}")