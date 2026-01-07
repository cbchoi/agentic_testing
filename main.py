import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool, RunPytestTool
from quality_standards import get_quality_prompt

load_dotenv()

TARGET_DIR = "target_apps/cloned_app"
TEST_FILE_REL = "test_quality_check.py"
TEST_FILE_ABS = os.path.join(TARGET_DIR, TEST_FILE_REL)


analyzer = Agent(
    role="ISO/IEC 25010 품질 인증 심사원",
    goal=f"pygame 프로젝트 소스코드를 정밀 분석하여 품질 표준 만족 여부를 증명하라: {get_quality_prompt()}",
    backstory=(
        "너는 소프트웨어 품질 국제 표준 전문가야.\n"
        "직접 코드를 수정하지는 않지만, 독해를 통해 함수의 라인 수, 복잡도, 예외 처리 위치를 정확히 찾아내어\n"
        "수치 중심의 리포트를 작성한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ListFilesTool(), ReadFileTool()],
    config={"temperature": 0.0},
)

test_creator = Agent(
    role="Pytest 기반 테스트 코드 생성 전문가",
    goal="분석 리포트에서 발견된 품질 항목 및 결함을 검증하는 실행 가능한 테스트 코드를 작성하라.",
    backstory=(
        "너는 전문적인 파이썬 테스트 엔지니어다.\n"
        "품질 분석 리포트를 읽고, pygame 프로젝트 전반에 적용 가능한 범용 품질 pytest를 작성한다.\n"
        "테스트는 반드시 import/실행 없이 정적/준정적 방식으로 작성한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ListFilesTool(), ReadFileTool(), WriteFileTool()],
    config={"temperature": 0.0},
)

test_reporter = Agent(
    role="테스트 자동화 및 결과 분석가",
    goal="작성된 테스트 코드를 실행하고, 그 결과를 바탕으로 최종 TC 리포트를 작성하라.",
    backstory=(
        "너는 테스트 자동화 전문가야.\n"
        "생성된 pytest 파일을 실행하여 성공/실패 여부를 확인하고,\n"
        "이를 사용자가 읽기 쉬운 최종 테스트 결과 보고서(TC Report)로 정리한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ReadFileTool(), RunPytestTool()],
    config={"temperature": 0.0},
)


github_analysis_task = Task(
    description=f"""
[0. 반드시 이 순서로 진행]
1) ListFilesTool로 '{TARGET_DIR}' 폴더의 파일 목록을 먼저 확보하라.
   - list_files 인자: '{TARGET_DIR}'
   - 결과 원문을 근거로 삼아야 한다.
2) 위 목록에서 분석할 .py 파일 후보(최소 2개)를 선정하라.
3) ReadFileTool로 선정된 파일 내용을 읽어라.
   - 근거에는 "파일 경로 + 줄번호 + 코드 일부"가 반드시 포함되어야 한다.

[중요: 금지]
- "권한 문제/파일 접근 불가" 같은 결론을 내리려면,
  (1) list_files 결과 원문,
  (2) read_file 결과 원문(오류 메시지 포함)
  을 보고서에 포함해야 한다.
- 위 원문 인용 없이 권한/부재 결론을 내리는 것은 금지한다.

[1. 분석 대상]
- 대상 폴더: '{TARGET_DIR}'
- 특정 파일명(예: game.py/main.py)을 고정하지 말고, 존재하는 파일을 기준으로 근거를 수집하라.
- pygame 프로젝트의 핵심 파일(엔트리/루프/이벤트/tick)을 자동으로 찾아 분석하라.

[2. 품질 판정 절대 기준]
- 다음 가이드라인을 엄격히 준수하여 Pass/Fail을 판정하라:
{get_quality_prompt()}

[판정 가이드라인]
- 모든 판정은 '본인의 상식'이 아닌, 제공된 '수치 기준'과의 수학적 비교로만 결정하라.
- 함수명/변수명/엔트리포인트는 절대 추측하지 말고, 실제 코드에 존재하는 식별자만 사용하라.
- 근거에는 반드시 파일 경로와 줄번호를 포함하라.

[3. 분석 포인트(범용 pygame)]
- 신뢰성: 예외 처리(try/except, KeyboardInterrupt 등) 존재 여부
- 성능 효율성: tick 사용 여부 및 FPS 값 후보
- 기능 적합성: 종료 조건(QUIT 처리, running False, sys.exit 등) 존재 여부
- 유지보수성: 주요 함수 LOC/복잡도(제어문 기반 근사치) 측정

[4. 출력 형식]
반드시 한국어로 작성하며, 아래 섹션 구조를 유지하라.
### [품질 검증 명세서]
- 품질 특성: [항목명]
- 검증 대상: [파일/함수/줄번호]
- 최종 판정: [Pass 또는 Fail]
- 데이터 근거: [측정된 실제 수치 및 코드 증거]
""",
    expected_output="가이드라인 수치와 실제 소스 코드가 결합된 상세 분석 리포트",
    agent=analyzer,
    output_file="quality_analysis_report.md",
)


test_generation_task = Task(
    description=f"""
[중요: 파일 위치]
- 반드시 '{TEST_FILE_ABS}' 1개 파일만 WriteFileTool로 생성하라.

[중요: pytest 구조 강제 규칙]
- 테스트 간 공유 값(core_files 등)은 전역 변수 금지. 반드시 pytest fixture로 제공하라.
- fixture 형식 고정:
  @pytest.fixture(scope="session")
  def core_files():
      ...
      return core_files_list

- 모든 테스트 함수는 반드시 인자로 core_files를 받아 사용하라.
- test_00이 먼저 실행되어 값을 넘긴다 같은 구조는 금지한다.

[필수 import]
- 생성 파일 상단에 반드시 import pytest, import re 를 포함하라.

[필수 self-check]
- WriteFileTool로 작성 직후, ReadFileTool로 '{TEST_FILE_ABS}'를 다시 읽어서 아래를 확인하라.
  (1) '@pytest.fixture' 문자열 존재
  (2) 'def core_files' 존재
  (3) 'import re' 존재
  (4) 'def test_' 함수가 5개 존재(아래 이름 고정)
- 하나라도 없으면 즉시 다시 작성하라.

[목표]
- pygame 프로젝트에도 적용 가능한 범용 품질 pytest 1개를 작성하라.
- 정적/준정적(파일 텍스트 + AST) 분석만 수행한다. 대상 프로젝트 import/실행 금지.

[절대 금지]
- if __name__ == "__main__": 금지
- print 중심 실행 로직 금지
- 대상 프로젝트 import 금지
- pygame 실행/루프 호출 금지
- 전역 객체 접근 금지

[필수 구현: pytest 테스트 함수 5개 이름 고정]
1) test_00_discovery_sanity
2) test_01_reliability_keyboard_interrupt
3) test_02_performance_fps_tick_range
4) test_03_maintainability_loc_and_complexity_approx
5) test_04_functional_suitability_game_over_presence

[탐색 구현 강제]
- pathlib.Path 사용
- base_dir은 CWD 의존 금지:
  project_root = Path(__file__).resolve().parent
  base_dir = project_root
- *.py 파일 재귀 탐색하되 venv/.git/__pycache__ 경로 제외
- test_*.py 파일은 무조건 제외(특히 test_quality_check.py 자신)

[core files 선정(점수화)]
- 각 파일 텍스트 기반으로 아래를 점수화해 Top 1~3개를 core_files로 선정하라:
  1) "import pygame" 또는 "from pygame"
  2) "if __name__ == '__main__'"
  3) 파일명이 main.py/game.py/app.py/run.py/__main__.py
  4) ".tick(" 또는 "tick_busy_loop("
- 점수가 전부 0이면, 전체 py 파일 중 앞에서 3개라도 core_files로 잡아 최소 동작 보장.
- core_files에는 반드시 "게임 코드 파일"이 우선 포함되도록 하라(테스트 파일 제외 규칙 때문에 자연스럽게 됨).

[검증 규칙]
A) 신뢰성
- core_files 중 최소 1개에서 KeyboardInterrupt 또는 try/except 흔적이 있어야 한다.

B) 성능 효율성
- 아래 정규식으로 tick 값을 찾는다(변수명 고정 금지):
  - r'\\b\\w+\\.tick\\(\\s*(\\d+)\\s*\\)'
  - r'\\b\\w+\\.tick_busy_loop\\(\\s*(\\d+)\\s*\\)'
- 단, 해당 파일에 'import pygame' 또는 'from pygame'가 있을 때만 tick을 유효로 인정한다.
- 하나도 못 찾으면 Fail.
- 값이 1~240 범위를 벗어나면 Fail.
- 실패 메시지에 (file, lineno, value) 포함.

C) 유지보수성(근사)
- AST로 FunctionDef 수집
- LOC = end_lineno - lineno + 1
- complexity 근사 = 1 + 제어문/논리연산(if/for/while/try/with/match/boolop) 카운트
- 임계치: LOC>50 또는 complexity>15 이면 Fail 처리(어떤 함수/파일/LOC/complexity 포함)

D) 기능 적합성(종료 조건 존재성)
- 키워드(lives/life/health/hp/game_over/running/over/dead/is_over/QUIT/sys.exit/pygame.quit)와
  패턴(<=0,==0,not running, pygame.QUIT, sys.exit(), pygame.quit(), break, return)의 조합이
  최소 1개라도 라인 단위로 존재하면 Pass.
- 아무것도 없으면 Fail.

[assert proof 필수]
- 각 assert 실패 메시지에 다음을 포함하라:
  sys.executable, os.getcwd(), base_dir, py_file_count, core_files
""",
    expected_output="pytest가 정상 수집 가능한 test_quality_check.py (테스트 함수 5개 포함)",
    agent=test_creator,
    context=[github_analysis_task],
)


test_execution_task = Task(
    description=f"""
[역할]
- 너는 반드시 pytest를 '직접 실행'하는 에이전트다.
- 추측/요약으로 대체 금지. RunPytestTool 실행 결과가 근거다.

[실행 전 품질 게이트(최대 2회)]
- ReadFileTool로 '{TEST_FILE_ABS}'를 읽고 아래를 검사하라:
  1) '@pytest.fixture' 포함
  2) 'def core_files' 포함
  3) 'import re' 포함
  4) 'def test_' 함수 5개(이름 고정 5개) 존재
- 하나라도 실패하면, 에이전트2에게 재생성을 요청하고 다시 읽어 재검사하라.
- 이 반복은 최대 2회까지만 수행하라.

[권한/파일부재 결론 금지]
- '{TEST_FILE_ABS}'에 대해 "권한/부재" 결론을 내리려면,
  ReadFileTool 반환 원문(오류 포함)을 보고서에 포함해야 한다.

[실행]
- 반드시 RunPytestTool을 1회 이상 호출하라.
- 실행 인자(args)는 아래 중 하나만 사용:
  1) '{TEST_FILE_REL} -q'
  2) '-q'
- RunPytestTool은 '{TARGET_DIR}'을 CWD로 실행한다. 경로를 조합하거나 변경하지 마라.

[증명 로그]
- RunPytestTool 반환 문자열(PYTHON/CWD/PYTEST_VERSION/CMD/EXIT_CODE/STDOUT/STDERR)을 가공하지 말고 원문 그대로 보고서에 포함하라.

[판정]
- EXIT_CODE == 0 이면 "직접 실행 성공"
- EXIT_CODE != 0 이면 "직접 실행 실패"

[최종 보고서 형식]
--------------------------------------------------
# [최종 품질 통합 보고서]

## 1. 정적 분석 요약 (에이전트 1 결과)
- (주요 품질 특성별 Pass/Fail 요약 및 핵심 결함 코드 인용)

## 2. 동적 테스트 결과 요약
- **직접 실행 상태:** (직접 실행 성공 / 직접 실행 실패)
- **테스트 성공 개수:** (숫자) / **실패 개수:** (숫자)
- **검증 범위:** (이번 테스트가 커버한 항목)

## 3. pytest 실행 증명 로그 (원문)
- (RunPytestTool 반환값 전체)

## 4. 상세 실패 원인 및 기술 분석
- (실패 시 Traceback의 원인과 테스트 코드 결함/탐지 규칙 문제 여부를 먼저 점검)

## 5. 종합 판정 및 개선 권고
- **최종 품질 등급:** (우수/보통/미흡)
- **종합 판정:** (Pass / Fail)
- **판정 근거:** (정적 분석 수치 + 동적 실행 증거 결합)
- **우선 개선 권고 사항:** (1~2개)
--------------------------------------------------
""",
    expected_output="[최종 품질 통합 보고서] 형식을 준수한 최종 보고서",
    agent=test_reporter,
    context=[github_analysis_task, test_generation_task],
    output_file="final_tc_report.md",
)


qa_crew = Crew(
    agents=[analyzer, test_creator, test_reporter],
    tasks=[github_analysis_task, test_generation_task, test_execution_task],
    process=Process.sequential,
)

if __name__ == "__main__":
    print("### [AI QA Team] 품질 분석 및 테스트 케이스 생성 시작 ###")
    try:
        qa_crew.kickoff()
        print("\n### 작업 완료!")
        print("- 품질 리포트: quality_analysis_report.md")
        print(f"- 생성된 테스트 코드: {TEST_FILE_ABS}")
        print("- 최종 리포트: final_tc_report.md")
    except Exception as e:
        print(f"\n에러 발생: {e}")
