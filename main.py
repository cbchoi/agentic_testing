import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
import re
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool, RunPytestTool, RunWSLCommandTool
import json
from datetime import datetime, timezone
from quality_standards import get_quality_prompt, get_quality_spec, iso_spec
import time
from pathlib import Path

load_dotenv()

TARGET_ROOT = "target_apps"
TEST_FILE_REL = "tests/test_quality_check.py"

def iter_target_dirs(root: str):
    root_path = Path(root)
    if not root_path.exists():
        return []
    return sorted([p for p in root_path.iterdir() if p.is_dir()])

def detect_project_type(target_dir: str) -> str:
    p = Path(target_dir)

    # 1) Pygame 판별: requirements.txt 또는 import pygame
    req = p / "requirements.txt"
    if req.exists():
        try:
            if "pygame" in req.read_text(encoding="utf-8", errors="ignore").lower():
                return "game_pygame"
        except Exception:
            pass

    for py in p.rglob("*.py"):
        try:
            txt = py.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^\s*(import\s+pygame|from\s+pygame\s+import\s+)", txt, flags=re.MULTILINE):
                return "game_pygame"
        except Exception:
            continue

    # 2) C HTTP 서버 판별: Makefile + C 소스(또는 README 힌트)
    has_makefile = (p / "Makefile").exists() or (p / "makefile").exists()
    has_c = any(True for _ in p.rglob("*.c"))
    if has_makefile and has_c:
        return "c_http_server"

    for md in list(p.rglob("README*"))[:5]:
        try:
            t = md.read_text(encoding="utf-8", errors="ignore").lower()
            if "http" in t and ("server" in t or "httpd" in t):
                return "c_http_server"
        except Exception:
            continue

    return "game_pygame"


def make_paths(target_dir: str) -> dict:
    name = Path(target_dir).name
    logs_dir = Path("logs") / name
    logs_dir.mkdir(parents=True, exist_ok=True)

    test_file_abs = str(Path(target_dir) / TEST_FILE_REL)

    return {
        "TARGET_DIR": target_dir,
        "TARGET_NAME": name,
        "TEST_FILE_ABS": test_file_abs,

        "LOGS_DIR": str(logs_dir),
        "STATIC_JSON_PATH": str(logs_dir / "static_analysis.json"),
        "RUN_ARTIFACTS_PATH": str(logs_dir / "run_artifacts.json"),
        "RESULT_JSON_PATH": str(logs_dir / "result.json"),
        "QUALITY_MD_PATH": str(logs_dir / "quality_analysis_report.md"),
        "FINAL_MD_PATH": str(logs_dir / "final_tc_report.md"),
        "RESULT_KV_JSON_PATH": str(logs_dir / "result_kv.json"),
    }


# ----------------------------------------------------------------
# 1. Agents 설정: 페르소나와 전문성 강화
# ----------------------------------------------------------------
def build_crew_for_target(project_type: str, target_dir: str, paths: dict) -> Crew:
    analyzer = Agent(
        role="ISO/IEC 25010 품질 인증 심사원",
        goal=f"대상 프로젝트 소스코드를 정밀 분석하여 품질 표준 만족 여부를 증명하라: {get_quality_prompt(project_type)}",
        backstory=(
            "너는 소프트웨어 품질 국제 표준 전문가야. 주관적인 판단을 배제하고 오직 코드 데이터로만 말한다.\n"
            "독해를 통해 함수의 라인 수, 복잡도, 예외 처리 위치를 정확히 찾아내며,\n"
            "특히 변수(예: fps)가 사용된 경우 해당 변수의 실제 할당값을 역추적하여 수치화한다."
        ),
        llm="gpt-4o-mini",
        verbose=True,
        allow_delegation=False,
        tools=[
            ListFilesTool(allowed_root=target_dir),
            ReadFileTool(allowed_root=target_dir),
            RunWSLCommandTool(),
        ],
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
            """[HARNESS MANDATORY RULES]

            - You MUST use the shared harness located at tests/_harness.py.
            - You MUST import:
            from tests._harness import (
                resolve_target_dir, resolve_file, read_text_file,
                run_command3, find_pygame_entrypoint,
                summarize_exception
                )
            Hard requirements:
            1) All filesystem access MUST be derived from resolve_target_dir().
            - Forbidden: "target_apps/...", absolute paths, os.walk("target_apps")
            2) You MUST NOT call subprocess.run / subprocess.Popen directly.
            - Use run_command() from the harness.
            3) You MUST NOT use open() to read target files.
            - Use read_text_file() or resolve_file().
            4) tests/_harness.py must NOT be modified.
            5) The output MUST be valid Python code (no escaped quotes like \").
            6) If you use os/pathlib/re, you MUST import them explicitly.
        """
        ),
        llm="gpt-4o-mini",
        verbose=True,
        allow_delegation=False,
        tools=[
            ListFilesTool(allowed_root=target_dir),
            ReadFileTool(allowed_root=target_dir),
            WriteFileTool(),
        ],
        config={"temperature": 0.0},
    )

    test_reporter = Agent(
        role="테스트 자동화 및 결과 분석가",
        goal="작성된 테스트 코드를 실행하고, 그 결과를 바탕으로 최종 통합 품질 보고서를 작성하라.",
        backstory=(
            "너는 테스트 결과의 신뢰성을 책임진다. RunPytestTool의 실행 로그 원문을 훼손 없이 인용하며,\n"
            "테스트 실패 시 그것이 소스 코드의 결함인지, 테스트 코드 문법 오류인지 명확히 판별하여 보고한다."
        ),
        llm="gpt-4o-mini",
        verbose=True,
        allow_delegation=False,
        tools=[
            ListFilesTool(allowed_root=target_dir),
            ReadFileTool(allowed_root=target_dir),
            WriteFileTool(),
            RunPytestTool(),
        ],
        config={"temperature": 0.0},
    )

    github_analysis_task = Task(
        description=_analysis_task_description(project_type, target_dir),
        expected_output="static_analysis.json 형식의 JSON 배열",
        agent=analyzer,
        output_file=paths["STATIC_JSON_PATH"],
    )

    test_generation_task = Task(
        description=_test_generation_description(project_type, target_dir, paths["TEST_FILE_ABS"]),
        expected_output="pytest 테스트 코드 파일 생성 (순수 파이썬 코드)",
        agent=test_creator,
        output_file=paths["TEST_FILE_ABS"],
    )

    test_execution_task = Task(
        description=f"""
[실행 및 결과 수집]

0) 반드시 먼저 "{TEST_FILE_REL}" 파일을 read_file로 읽고, 아래 규칙으로 정제한 뒤 write_file로 같은 파일에 덮어써라.
   - 코드펜스(```/```python) 제거
   - JSON으로 감싸진 경우 문자열만 추출
   - 문서 전체에 "\\\\n"이 많이 있고 실제 줄바꿈이 거의 없으면 "\\\\n"을 실제 줄바꿈으로 치환
   - import/from이 시작되는 줄부터만 남김
   - 절대 os.chdir(wsl_path) 같은 코드를 넣지 마라 (Windows에서 WSL 경로 chdir 금지)
   - WSL 경로는 오직 "wsl bash -lc 'cd ... && ...'" 내부에서만 사용하라.
   - import는 표준 라이브러리 + pytest만 허용한다. (requests 금지)
   - "my_module", "my_function" 같은 placeholder는 절대 포함하면 안 된다.

   write_file 입력 형식: "{paths["TEST_FILE_ABS"]}|<정제된 파이썬 코드 전체>"

1) RunPytestTool을 다음 입력으로 실행하라:
   "{target_dir}|{TEST_FILE_REL} -q"

2) RunPytestTool의 실행 결과(반환값)를 반드시 변수로 받아라.
   그 다음 output_file에 "오직 JSON만" 저장하라. (설명/로그/툴 트레이스 금지)

   저장해야 하는 JSON 스키마는 아래와 같다:
   {{
     "exit_code": <int>,
     "stdout": "<string>",
     "stderr": "<string or empty>"
   }}

   - stdout/stderr는 가능한 그대로 전체를 넣어라.
   - JSON 외의 텍스트가 output_file에 섞이면 실패로 간주된다.
""",
        expected_output="JSON object containing exit_code and stdout/stderr.",
        agent=test_reporter,
        context=[github_analysis_task, test_generation_task],
        output_file=paths["RUN_ARTIFACTS_PATH"],
    )

    return Crew(
        agents=[analyzer, test_creator, test_reporter],
        tasks=[github_analysis_task, test_generation_task, test_execution_task],
        process=Process.sequential,
    )

# ----------------------------------------------------------------
# 2. Tasks 설정: 실행 순서와 제약 사항 명확화
# ----------------------------------------------------------------

def _analysis_task_description(project_type: str, target_dir: str) -> str:
    if project_type == "c_http_server":
        return f"""
[분석 대상 강제]
- 반드시 첫 번째 행동으로 list_files tool을 호출한다.
- list_files 호출 인자:
  directory_path = "{target_dir}"
- 너는 반드시 "{target_dir}" 디렉토리 하위의 파일만 분석해야 한다.
- "{target_dir}" 밖의 파일은 절대 읽지 말고, 언급하지 말고, 근거로 사용하지 마라.

[도구 사용 규칙 - 반드시 실행]
- 아래 WSL 명령을 반드시 실행해 근거 데이터를 확보하라.
  1) run_wsl_command: "{target_dir}|make"
  2) run_wsl_command: "{target_dir}|cppcheck --enable=warning,style,performance,portability --quiet ."
  3) run_wsl_command: "{target_dir}|lizard -l c -C 20 ."

[출력 포맷 안전 규칙]
- 마크다운 ```json 펜스를 쓰지 마라. 설명을 붙이지 마라.
- 오직 순수 JSON 배열만 출력하라.

[반드시 사용해야 할 항목 ID (id 필드에 아래 값만 사용)]
1. Maintainability.FunctionLOC
2. Maintainability.MainLoopComplexity
3. Reliability.FaultTolerance.ResourceLoading
4. FunctionalSuitability.HttpBasic

[출력 JSON 스키마 (필수)]
각 배열 원소는 다음 키를 반드시 포함해야 한다:
{{
  "id": "위의 항목 ID 중 하나",
  "quality_feature": "해당 특성명 (예: Maintainability)",
  "decision_rule": "적용된 수치 기준",
  "measurement_method": "측정 방식",
  "measured": "실측 수치 (숫자 또는 객체)",
  "final_judgment": "Pass 또는 Fail",
  "data_evidence": "근거 텍스트"
}}

[판정 규칙]
- LIZARD 결과에서:
  - FunctionLOC: 함수별 NLOC 중 최대값이 {get_quality_spec("c_http_server")["thresholds"]["loc_limit"]} 이하이면 Pass
  - MainLoopComplexity: 함수별 CCN 중 최대값이 {get_quality_spec("c_http_server")["thresholds"]["complexity_limit"]} 이하이면 Pass
- CPPCHECK 결과에서:
  - cppcheck 출력에 warning/issue가 있으면 warning_count를 계산하라.
  - warning_count <= {get_quality_spec("c_http_server")["thresholds"]["cppcheck_max_warnings"]} 이면 Pass

[주의]
- FunctionalSuitability.HttpBasic은 여기서 "측정 불가(동적 테스트에서 검증)"로 두되, 아래처럼 기록하라:
  - measured: {{"passed": 0, "failed": 0}}
  - final_judgment: "Fail"
  - data_evidence: "Will be evaluated by pytest execution output"
"""

    # -----------------------------
    # game_pygame 전용: 규칙/판정 추가 (C는 건드리지 않음)
    # -----------------------------
    game_spec = get_quality_spec("game")
    th = game_spec["thresholds"]
    loc_limit = th["loc_limit"]
    fps_min = th.get("fps_min", 30)

    return f"""
[분석 대상 강제]
- 반드시 첫 번째 행동으로 list_files tool을 호출한다.
- list_files 호출 인자:
  directory_path = "{target_dir}"
- 너는 반드시 "{target_dir}" 디렉토리 하위의 .py 파일만 분석해야 한다.
- "{target_dir}" 밖의 파일은 절대 읽지 말고, 언급하지 말고, 근거로 사용하지 마라.

[핵심 지시]
- 너는 quality_standards.py의 ExecSpec(=get_quality_spec("game")["checks"])에 정의된 항목을 그대로 따라야 한다.
- 아래 나열된 5개 ID는 모두 반드시 출력 배열에 포함해야 한다. (배열이 비면 실패)
  1) Maintainability.FunctionLOC
  2) Maintainability.MainLoopComplexity
  3) PerformanceEfficiency.TimeBehaviour
  4) Reliability.FaultTolerance.ResourceLoading
  5) FunctionalSuitability.StateTransitionValidation.ExitSignals

[측정/판정 규칙 (필수)]
- Maintainability.FunctionLOC:
  - method: AST로 FunctionDef별 LOC = end_lineno - lineno + 1 계산
  - rule: max(function_loc) <= {loc_limit} 이면 Pass
  - measured 예시: {{"max_loc": 42, "file": "main.py", "function": "update"}}

- Maintainability.MainLoopComplexity:
  - method: 최상위 While 중 가장 큰 While을 main loop로 보고,
    branch_count(if/elif/for/while/try/except 수), nesting_depth, cyclomatic_proxy를 계산
  - rule: ExecSpec의 rule( branch_count<=25 AND nesting_depth<=4 AND cyclomatic_proxy<=20 )을 그대로 적용
  - measured 예시: {{"branch_count": 10, "nesting_depth": 3, "cyclomatic_proxy": 12, "file": "game.py"}}

- PerformanceEfficiency.TimeBehaviour:
  - method: AST로 clock.tick(arg) 또는 fps 상수/대입 추적해서 resolved_fps 추정
  - rule: resolved_fps >= {fps_min} 이면 Pass
  - measured 예시: {{"min_resolved_fps": 60, "source": "clock.tick(60)", "file": "main.py"}}
  - fps를 정적으로 찾지 못하면 Fail로 두고 data_evidence에 "FPS not resolvable statically"를 남겨라.

- Reliability.FaultTolerance.ResourceLoading:
  - method: AST로 pygame.image.load / pygame.mixer.Sound / open(...) 같은 리소스 로딩 호출을 찾고,
    try/except 내부인지 검사
  - rule: 모든 리소스 로딩 호출이 try/except 내부면 Pass, 아니면 Fail
  - measured 예시: {{"unprotected_calls": 2, "examples": ["assets.py:load_image", "sound.py:init"]}}

- FunctionalSuitability.StateTransitionValidation.ExitSignals:
  - method: 텍스트 스캔으로 pygame.QUIT, sys.exit, running=False, quit() 패턴 탐지
  - rule: exit signal이 1개 이상 존재하면 Pass
  - measured 예시: {{"patterns": ["pygame.QUIT"], "file": "main.py"}}

[출력 포맷 안전 규칙 - 매우 중요]
- 오직 순수 JSON 배열만 출력하라. (설명/인사/markdown 금지)
- 각 원소는 아래 스키마를 반드시 만족해야 한다:
{{
  "id": "위의 항목 ID 중 하나",
  "quality_feature": "해당 특성명",
  "decision_rule": "적용된 수치 기준",
  "measurement_method": "측정 방식",
  "measured": "실측 수치",
  "final_judgment": "Pass 또는 Fail",
  "data_evidence": "근거 텍스트"
}}
- JSON 배열이 비면 안 된다. 측정이 어려우면 Fail로 기록하고 근거(data_evidence)를 남겨라.
"""


def _test_generation_description(project_type: str, target_dir: str, test_file_abs: str) -> str:
    if project_type != "c_http_server":
        return _original_game_description(project_type, target_dir, test_file_abs)

    return f"""
You are a QA agent for a C-based HTTP server project.

Target project directory:
{target_dir}

Write the pytest file to:
{test_file_abs}

MANDATORY PATH RULE:
- The output file path MUST be exactly: {test_file_abs}
- The file MUST be under the "tests/" directory.
- The file name MUST start with "test_" so pytest can discover it.

========================
ABSOLUTE RULES (MANDATORY)
========================
- Use ONLY Python standard library + pytest.
- Do NOT use subprocess in the test file.
- Do NOT hardcode 'target_apps/...' or any absolute paths.
- Do NOT open files with open(). Use read_text_file() if needed.
- Use ONLY APIs from tests._harness:
  - resolve_target_dir(), resolve_file(), read_text_file()
  - run_command(), start_process(), stop_process()
  - wait_for_tcp(), http_get_raw()
  - summarize_exception()

- If build is needed, run it via run_command([...], cwd=TARGET_DIR).
- For server run: start_process([...], cwd=TARGET_DIR) and later stop_process(handle).

========================
TOP-OF-FILE TEMPLATE (MANDATORY)
========================
Your pytest file MUST start with EXACTLY these lines (no indentation before them):

from tests._harness import (
    resolve_target_dir, resolve_file, read_text_file,
    run_command, start_process, stop_process,
    wait_for_tcp, http_get_raw,
    summarize_exception,
)


CRITICAL FORMAT RULES:
- The file MUST start at line 1 with: "from tests._harness import ("
- Do NOT define any helper functions (no wait_for_port, no socket usage, no sys.path edits).
- Do NOT import pytest explicitly.
- Do NOT reference undefined variables (no server_root).
- Do NOT include any stray lines, partial lists, or dangling parentheses.
- Only use wait_for_tcp and http_get_raw from the harness.
- http_get_raw must be called as: http_get_raw("127.0.0.1", port, "/")

TARGET_DIR = resolve_target_dir()

========================
TEST CONTENT REQUIREMENTS
========================
- Generate at least ONE pytest test function named test_http_server_smoke.
- The test MUST:
  1) Optionally build the target
  2) Start the server
  3) Wait for TCP port to open
  4) Send HTTP GET "/" using http_get_raw
  5) Assert response contains "HTTP/"
  6) Always stop the server in finally

========================
OUTPUT (MANDATORY)
========================
- Exactly one pytest file
- Pure Python code only
- No markdown, no examples, no explanations
"""



def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _load_json_lenient_from_text(text: str):
    """
    텍스트에서 JSON을 최대한 복구한다.
    - 정상 JSON(객체/배열) 지원
    - '연속된 여러 JSON 객체'도 모두 파싱해서 list로 반환 지원
    """
    if not text:
        return None

    text = text.strip()

    # code fence 제거
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    # JSON 주석 제거 (//... , /* ... */)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # 첫 JSON 시작 위치
    m = re.search(r"[\{\[]", text)
    if not m:
        return None

    s = text[m.start():].lstrip()
    decoder = json.JSONDecoder()

    # 1) 먼저 "배열/객체 1개"로 파싱 시도
    try:
        obj, idx = decoder.raw_decode(s)
        # 뒤에 의미 있는 텍스트가 없으면 그대로 반환
        tail = s[idx:].strip()
        if not tail:
            return obj
        # 뒤에 또 JSON이 이어지는 형태면 아래 multi-parse로 진행
    except Exception:
        obj = None

    # 2) 여러 JSON 객체가 연속으로 이어진 경우: 끝까지 파싱해서 list로 반환
    items = []
    i = 0
    n = len(s)

    while i < n:
        # 공백/구분자 제거
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break

        # 다음 JSON 시작 찾기
        if s[i] not in "{[":
            m2 = re.search(r"[\{\[]", s[i:])
            if not m2:
                break
            i += m2.start()

        try:
            val, j = decoder.raw_decode(s[i:])
            items.append(val)
            i += j
        except Exception:
            break

    if items:
        # 배열 하나가 items[0]로 잡힌 케이스면 그걸 그대로 반환
        if len(items) == 1 and isinstance(items[0], (list, dict)):
            return items[0]
        return items

    return obj


def _load_json_if_exists(*paths: str):
    for p in paths:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()

            # 엄격 파싱 먼저 시도
            try:
                return json.loads(raw), p
            except Exception as e1:
                # 실패하면 관대한 파싱(첫 JSON만)
                data = _load_json_lenient_from_text(raw)
                if data is not None:
                    return data, p

                # 완전 실패 시, main이 죽지 않도록 에러 래핑
                preview = raw.strip().replace("\r\n", "\n")
                return {
                    "_parse_error": f"{type(e1).__name__}: {e1}",
                    "_path": p,
                    "_raw_preview": preview[:2000],
                }, p

    return None, None

def map_project_type_to_spec_key(project_type: str) -> str:
    if project_type in ["game_pygame", "game"]:
        return "game"
    if project_type in ["c_http_server"]:
        return "c_http_server"
    return "game"


def _parse_pytest_counts(stdout: str) -> dict:
    # Example: "4 passed in 0.03s"
    passed = failed = skipped = 0
    if not stdout:
        return {"passed": 0, "failed": 0, "skipped": 0}
    m = re.search(r"(\d+)\s+passed", stdout)
    if m: passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", stdout)
    if m: failed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", stdout)
    if m: skipped = int(m.group(1))
    return {"passed": passed, "failed": failed, "skipped": skipped}

def _normalize_run_to_characteristics(run_data: dict, spec_checks: list) -> list:
    out = []
    if not run_data or not isinstance(run_data, dict):
        return out

    stdout_text = (run_data.get("stdout") or "")
    stderr_text = (run_data.get("stderr") or "")
    exit_code = run_data.get("exit_code")

    # 1) 항상 생성되는 "pytest 실행 자체" 체크
    if exit_code is not None:
        out.append(
            {
                "id": "TestExecution.PytestRun",
                "type": "run",
                "characteristic": "TestExecution",
                "metric": "pytest_exit_code",
                "measured": {"exit_code": exit_code},
                "rule": "pytest exit code must be 0",
                "method": "PYTEST",
                "pass": bool(exit_code == 0),
                "weight": 0.0,  # 점수에는 영향 X, 해석용
                "evidence": {
                    "stdout_tail": stdout_text[-2000:],
                    "stderr_tail": stderr_text[-2000:],
                },
            }
        )

    # 2) spec에 정의된 PYTEST 체크들(있다면)도 기존 방식으로 계속 지원
    counts = _parse_pytest_counts(stdout_text)

    for chk in (spec_checks or []):
        cid = chk.get("id")
        method = (chk.get("method") or "")
        metric = chk.get("metric")

        if not cid:
            continue
        if "PYTEST" not in method.upper():
            continue

        passed = int(counts.get("passed", 0))
        failed = int(counts.get("failed", 0))
        skipped = int(counts.get("skipped", 0))

        # 실패가 0이고, 최소 1개라도 passed가 있어야 Pass로 간주
        is_pass = (failed == 0 and passed >= 1)

        out.append(
            {
                "id": cid,
                "metric": metric,
                "measured": {"passed": passed, "failed": failed, "skipped": skipped},
                "rule": chk.get("rule"),
                "method": chk.get("method"),
                "pass": bool(is_pass),
                "evidence": {
                    "pytest_counts": counts,
                    "stdout_tail": stdout_text[-2000:],
                    "stderr_tail": stderr_text[-2000:],
                },
                "weight": chk.get("weight", 0),
            }
        )

    return out

def ensure_harness_exists(project_root: str) -> None:
    from pathlib import Path

    root = Path(project_root).resolve()
    tests_dir = root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # tests 패키지 안정화
    (tests_dir / "__init__.py").touch(exist_ok=True)

    harness_path = tests_dir / "_harness.py"

    def _upgrade_harness_if_needed(path: Path) -> None:
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        needs = [
            "def wait_for_tcp(",
            "def http_get_raw(",
            "def start_process(",
            "def stop_process(",
        ]
        if all(k in src for k in needs):
            return

        patch = """
# --- AUTO-ADDED: C/HTTP helpers (harness upgrade) ---
from dataclasses import dataclass
import socket

@dataclass
class ProcessHandle:
    popen: object
    cmd: list[str]
    cwd: str

def start_process(cmd: list[str], cwd: Path | None = None) -> ProcessHandle:
    cwd = cwd or resolve_target_dir()
    p = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return ProcessHandle(popen=p, cmd=cmd, cwd=str(cwd))

def stop_process(h: ProcessHandle, timeout_sec: int = 3) -> RunResult:
    start = time.time()
    p = h.popen
    try:
        if getattr(p, "poll")() is None:
            try:
                p.terminate()
            except Exception:
                pass
        try:
            out, err = p.communicate(timeout=timeout_sec)
            return RunResult(
                exit_code=int(getattr(p, "returncode", 0) or 0),
                stdout=out or "",
                stderr=err or "",
                duration_sec=time.time() - start,
                timed_out=False,
            )
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
            return RunResult(
                exit_code=124,
                stdout="",
                stderr="stop_process_timeout_or_error",
                duration_sec=time.time() - start,
                timed_out=True,
            )
    finally:
        try:
            if getattr(p, "poll")() is None:
                p.kill()
        except Exception:
            pass

def wait_for_tcp(host: str, port: int, timeout_sec: int = 5) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def http_get_raw(host: str, port: int, path: str = "/", timeout_sec: int = 3) -> str:
    req = (
        f"GET {path} HTTP/1.0\\r\\n"
        f"Host: {host}\\r\\n"
        f"Connection: close\\r\\n\\r\\n"
    )
    with socket.create_connection((host, port), timeout=timeout_sec) as s:
        s.sendall(req.encode("ascii", errors="ignore"))
        s.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")
# --- END AUTO-ADDED ---
"""
        path.write_text(src.rstrip() + "\n" + patch.lstrip(), encoding="utf-8")

    # 이미 있으면 업그레이드만 하고 끝
    if harness_path.exists():
        _upgrade_harness_if_needed(harness_path)
        return

    # 1) repo 내 "정식 하네스 원본"이 있으면 복사 후 업그레이드
    harness_code = (Path(__file__).resolve().parent / "tests" / "_harness.py")
    if harness_code.exists():
        harness_path.write_text(harness_code.read_text(encoding="utf-8"), encoding="utf-8")
        _upgrade_harness_if_needed(harness_path)
        return

    # 2) fallback: enforce_harness_import()가 요구하는 API를 전부 포함한 하네스
    fallback = """\
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import time
import socket
from typing import Optional, Tuple, List, Union


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool


def resolve_target_dir(env_key: str = "TARGET_DIR") -> Path:
    v = os.getenv(env_key)
    if v:
        return Path(v).resolve()
    return Path(__file__).resolve().parents[1]


def resolve_file(path: Union[str, Path], base: Optional[Path] = None) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    base = base or resolve_target_dir()
    return (base / p).resolve()


def read_text_file(path: Union[str, Path], base: Optional[Path] = None, encoding: str = "utf-8") -> str:
    p = resolve_file(path, base)
    return p.read_text(encoding=encoding)


def run_command(cmd: List[str], cwd: Optional[Path] = None, timeout_sec: int = 10) -> RunResult:
    cwd = cwd or resolve_target_dir()

    start = time.time()
    proc: Optional[subprocess.Popen] = None

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            out, err = proc.communicate(timeout=timeout_sec)
            return RunResult(
                exit_code=int(proc.returncode or 0),
                stdout=out or "",
                stderr=err or "",
                duration_sec=time.time() - start,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
                out, err = proc.communicate(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                out, err = "", ""
            return RunResult(
                exit_code=124,
                stdout=out or "",
                stderr=err or "",
                duration_sec=time.time() - start,
                timed_out=True,
            )
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass


def summarize_exception(stdout: str, stderr: str) -> Tuple[str, str]:
    blob = (stdout or "") + "\\n" + (stderr or "")
    for pat, label in [
        (r"NameError:.*", "NameError"),
        (r"ImportError:.*", "ImportError"),
        (r"ModuleNotFoundError:.*", "ModuleNotFoundError"),
        (r"FileNotFoundError:.*", "FileNotFoundError"),
        (r"SyntaxError:.*", "SyntaxError"),
    ]:
        m = re.search(pat, blob)
        if m:
            return label, m.group(0).strip()
    tail = blob.strip().splitlines()[-1] if blob.strip() else ""
    return "UnknownError", tail


@dataclass
class ProcessHandle:
    popen: object
    cmd: list[str]
    cwd: str


def start_process(cmd: list[str], cwd: Path | None = None) -> ProcessHandle:
    cwd = cwd or resolve_target_dir()
    p = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return ProcessHandle(popen=p, cmd=cmd, cwd=str(cwd))


def stop_process(h: ProcessHandle, timeout_sec: int = 3) -> RunResult:
    start = time.time()
    p = h.popen
    try:
        if getattr(p, "poll")() is None:
            try:
                p.terminate()
            except Exception:
                pass
        try:
            out, err = p.communicate(timeout=timeout_sec)
            return RunResult(
                exit_code=int(getattr(p, "returncode", 0) or 0),
                stdout=out or "",
                stderr=err or "",
                duration_sec=time.time() - start,
                timed_out=False,
            )
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
            return RunResult(
                exit_code=124,
                stdout="",
                stderr="stop_process_timeout_or_error",
                duration_sec=time.time() - start,
                timed_out=True,
            )
    finally:
        try:
            if getattr(p, "poll")() is None:
                p.kill()
        except Exception:
            pass


def wait_for_tcp(host: str, port: int, timeout_sec: int = 5) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def http_get_raw(host: str, port: int, path: str = "/", timeout_sec: int = 3) -> str:
    req = (
        f"GET {path} HTTP/1.0\\r\\n"
        f"Host: {host}\\r\\n"
        f"Connection: close\\r\\n\\r\\n"
    )
    with socket.create_connection((host, port), timeout=timeout_sec) as s:
        s.sendall(req.encode("ascii", errors="ignore"))
        s.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")
"""
    harness_path.write_text(fallback, encoding="utf-8")

def dedupe_characteristics(characteristics: list) -> list:
    """
    Same id can appear from static + run.
    Prefer run(PYTEST) result over static placeholder.
    """
    by_id = {}
    for c in characteristics:
        cid = c.get("id")
        if not cid:
            continue

        prev = by_id.get(cid)
        if not prev:
            by_id[cid] = c
            continue

        # prefer run type
        if (prev.get("type") != "run") and (c.get("type") == "run"):
            by_id[cid] = c
            continue

        # prefer PYTEST method
        prev_m = (prev.get("method") or "").upper()
        cur_m = (c.get("method") or "").upper()
        if ("PYTEST" not in prev_m) and ("PYTEST" in cur_m):
            by_id[cid] = c
            continue

    return list(by_id.values())


def enforce_harness_import(test_code: str) -> str:
    header = (
        "from tests._harness import (\n"
        "    resolve_target_dir,\n"
        "    resolve_file,\n"
        "    read_text_file,\n"
        "    run_command,\n"
        "    run_command3,\n"
        "    find_pygame_entrypoint,\n"
        "    summarize_exception,\n"
        "    start_process,\n"
        "    stop_process,\n"
        "    wait_for_tcp,\n"
        "    http_get_raw,\n"
        ")\n"
        "TARGET_DIR = resolve_target_dir()\n\n"
    )

    lines = test_code.splitlines()
    body = []

    for ln in lines:
        s = ln.strip()
        if s.startswith("from tests._harness import"):
            continue
        if s.startswith("TARGET_DIR ="):
            continue
        body.append(ln)

    return header + "\n".join(body).lstrip()


def force_trim_test_to_harness_import(test_file_abs: str) -> None:
    import re

    raw = Path(test_file_abs).read_text(encoding="utf-8", errors="ignore")

    # "from tests._harness import (" 라인부터 끝까지 강제 트림
    m = re.search(r"^from\s+tests\._harness\s+import\s*\(", raw, flags=re.MULTILINE)
    if not m:
        return  # 못 찾으면 그대로 둠 (preflight/validate에서 잡히게)

    trimmed = raw[m.start():].lstrip()
    Path(test_file_abs).write_text(trimmed.rstrip() + "\n", encoding="utf-8", errors="ignore")



def validate_harness_compliance(test_path: str) -> None:
    code = open(test_path, "r", encoding="utf-8").read()

    # 테스트 파일에서 직접 OS/프로세스 제어 금지: 하네스 API만 사용하게 강제
    forbidden = [
        "target_apps/",
        "target_apps\\",

        # subprocess를 직접 쓰는 순간 하네스 위반
        "import subprocess",
        "subprocess.",

        # 파일 직접 열기 금지(하네스의 read_text_file 사용)
        "open(",

        # 하드코딩 탐색 금지(타겟 루트는 TARGET_DIR/resolve_target_dir로만)
        "os.walk('target_apps",
        'os.walk("target_apps',
    ]

    missing_required = [
        "from tests._harness import",
        "resolve_target_dir",
    ]

    for req in missing_required:
        if req not in code:
            raise RuntimeError(f"[HARNESS_VIOLATION] missing_required={req}")

    for bad in forbidden:
        if bad in code:
            raise RuntimeError(f"[HARNESS_VIOLATION] forbidden_pattern_found={bad}")


def _match_check_id(static_item: dict, spec_checks: list) -> str:
    """
    static_analysis.json item format (your current):
      {
        "quality_feature": "Reliability",
        "decision_rule": "...",
        "measurement_method": "...",
        "final_judgment": "Pass|Fail",
        ...
      }
    We map it to spec.checks[*].id by:
      1) exact match on rule+method
      2) heuristic match on decision_rule keywords
      3) fallback by quality_feature order
    """
    rule = (static_item.get("decision_rule") or "").strip()
    method = (static_item.get("measurement_method") or "").strip()
    qf = (static_item.get("quality_feature") or "").strip()

    # 1) strict match on rule+method
    for c in spec_checks:
        if (c.get("rule") or "").strip() == rule and (c.get("method") or "").strip() == method:
            return c.get("id")

    # 2) heuristics by rule/method text
    rule_l = rule.lower()
    method_l = method.lower()

    if "function_loc" in rule_l or "functiondef" in method_l:
        return "Maintainability.FunctionLOC"
    if "branch_count" in rule_l or "top-level while" in method_l or "largest top-level while" in method_l:
        return "Maintainability.MainLoopComplexity"
    if "resolved_fps" in rule_l or "clock.tick" in method_l or "fps" in rule_l:
        return "PerformanceEfficiency.TimeBehaviour"
    if "resource" in rule_l or "pygame.image.load" in method_l or "mixer.sound" in method_l or "open(" in method_l:
        return "Reliability.FaultTolerance.ResourceLoading"
    if "exit signal" in rule_l or "pygame.quit" in method_l or "pygame.quit" in rule_l:
        return "FunctionalSuitability.StateTransitionValidation.ExitSignals"

    # 3) fallback by quality_feature
    by_qf = {
        "Maintainability": ["Maintainability.FunctionLOC", "Maintainability.MainLoopComplexity"],
        "PerformanceEfficiency": ["PerformanceEfficiency.TimeBehaviour"],
        "Reliability": ["Reliability.FaultTolerance.ResourceLoading"],
        "FunctionalSuitability": ["FunctionalSuitability.StateTransitionValidation.ExitSignals"],
    }
    candidates = by_qf.get(qf)
    if candidates:
        # choose first unused if possible
        used = set()
        # We'll compute used later; here just return first candidate
        return candidates[0]

    # last fallback: unknown
    return f"UNKNOWN::{qf or 'Unknown'}"

def _normalize_static_to_characteristics(static_list: list, spec_checks: list) -> list:
    characteristics = []
    used_ids = set()

    for item in static_list:
        cid = item.get("id") or _match_check_id(item, spec_checks)
        # try not to duplicate ids
        if cid in used_ids:
            # allow duplicates but make them unique
            suffix = 2
            while f"{cid}#{suffix}" in used_ids:
                suffix += 1
            cid = f"{cid}#{suffix}"
        used_ids.add(cid)

        judgment = (item.get("final_judgment") or "").strip().lower()
        passed = True if judgment == "pass" else False if judgment == "fail" else None

        characteristics.append({
            "id": cid,
            "type": "static",
            "characteristic": item.get("quality_feature"),
            "metric": None,
            "measured": item.get("data_evidence"),
            "rule": item.get("decision_rule"),
            "method": item.get("measurement_method"),
            "pass": passed,
            "evidence": {
                "verification_target": item.get("verification_target"),
            },
        })

    # attach weights from spec if id matches exactly
    weight_by_id = {c["id"]: c.get("weight", 0) for c in spec_checks if c.get("id")}
    for ch in characteristics:
        base_id = ch["id"].split("#")[0]
        ch["weight"] = weight_by_id.get(base_id, 0)

    return characteristics

def classify_failure(characteristic: dict, run_data: dict, project_type: str) -> dict:
    # Pass면 분류 불필요
    if characteristic.get("pass") is True:
        return characteristic

    cid = (characteristic.get("id") or "")
    rule = (characteristic.get("rule") or "")
    measured = characteristic.get("measured")
    measured_s = "" if measured is None else str(measured)

    stdout = ""
    stderr = ""
    if isinstance(run_data, dict):
        stdout = run_data.get("stdout") or ""
        stderr = run_data.get("stderr") or ""

    blob = (stdout + "\n" + stderr).lower()
    measured_l = measured_s.lower()
    rule_l = rule.lower()

    # 기본값
    failure_type = "SYSTEM_DEFECT"
    responsibility = "TARGET_SYSTEM"
    reason = "Failed the decision rule."

    # (추가) 포트 리슨 대기 타임아웃은 가정 위반
    if "wait_for_tcp timeout" in blob or "not listening" in blob:
        failure_type = "TEST_ASSUMPTION_VIOLATION"
        responsibility = "QA_AGENT"
        reason = "Port/listen assumption mismatch (server may be running on a different port or needs args)."

    # (1) 테스트 산출물 오류: NameError/ImportError/SyntaxError 등
    is_pytest_check = "PYTEST" in (characteristic.get("method") or "").upper()

    # (1-0) pygame 의존성 누락은 환경 책임
    if is_pytest_check:
        if ("modulenotfounderror" in blob) and (
            ("no module named 'pygame'" in blob)
            or ('no module named "pygame"' in blob)
            or ("no module named pygame" in blob)
        ):
            failure_type = "ENVIRONMENT_DEPENDENCY_MISSING"
            responsibility = "EXECUTION_ENVIRONMENT"
            reason = "Pygame dependency is missing (or subprocess used a different Python without pygame)."

    # (1-1) 그 외 NameError/ImportError/SyntaxError는 테스트 산출물 책임
    if (
        is_pytest_check
        and failure_type == "SYSTEM_DEFECT"  # 이미 (1-0)에서 분류했으면 덮어쓰지 않음
        and any(x in blob for x in ["nameerror", "importerror", "modulenotfounderror", "syntaxerror"])
    ):
        failure_type = "TEST_ARTIFACT_INVALID"
        responsibility = "TEST_GENERATOR"
        reason = "Pytest failure indicates invalid generated test code (missing import/syntax/etc.)."
    
    # (2-0) 분석 데이터 부족은 분석 한계로 분류
    if failure_type == "SYSTEM_DEFECT" and (
        "not enough function loc data available" in measured_l
        or "not enough complexity data available" in measured_l
    ):
        failure_type = "ANALYSIS_LIMITATION"
        responsibility = "QA_AGENT"
        reason = measured_s


    # (2) 분석 한계: 정적으로 결론 못 내림
    if failure_type == "SYSTEM_DEFECT" and (
        "not resolvable statically" in measured_l
        or "cannot be resolved" in measured_l
    ):
        failure_type = "ANALYSIS_LIMITATION"
        responsibility = "QA_AGENT"
        reason = measured_s or "Not resolvable statically."

    # (3) 가정 위반: ExitSignals 미검출은 설계일 수도 있음
    if cid.startswith("FunctionalSuitability.StateTransitionValidation.ExitSignals"):
        if "at least one exit signal exists" in rule_l and (measured_s.strip() in ["", "0", "none", "[]"]):
            failure_type = "TEST_ASSUMPTION_VIOLATION"
            responsibility = "QA_AGENT"
            reason = "No explicit exit signal detected; target may be designed as infinite-loop runtime."

    characteristic["failure_type"] = failure_type
    characteristic["responsibility"] = responsibility
    characteristic["failure_reason"] = reason
    return characteristic


def _compute_summary(characteristics: list, grading: dict) -> dict:
    total_weight = 0.0
    passed_weight = 0.0

    for ch in characteristics:
        w = float(ch.get("weight", 0) or 0)
        total_weight += w
        if ch.get("pass") is True:
            passed_weight += w

    score = (passed_weight / total_weight) if total_weight > 0 else 0.0

    grade_thresholds = (grading or {}).get("grade_thresholds") or {"우수": 0.85, "보통": 0.7, "미흡": 0.0}
    # pick highest grade that score >= threshold
    grade = None
    for g, th in sorted(grade_thresholds.items(), key=lambda x: x[1], reverse=True):
        if score >= float(th):
            grade = g
            break
    grade = grade or "미흡"

    overall_pass = all(ch.get("pass") is True for ch in characteristics if ch.get("weight", 0) > 0)

    return {
        "score": round(score, 4),
        "grade": grade,
        "overall_pass": bool(overall_pass),
        "passed_weight": round(passed_weight, 4),
        "total_weight": round(total_weight, 4),
    }

def render_md_reports(result: dict, out_quality_md: str, out_final_md: str) -> None:
    chs = result.get("characteristics") or []
    summary = result.get("summary") or {}
    run = result.get("run_log") or result.get("run") or {} 
    stdout_text = run.get("stdout") or ""

    failing = [c for c in chs if c.get("pass") is False]
    passing = [c for c in chs if c.get("pass") is True]

    def _md_table(rows: list) -> str:
        lines = [
            "| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |",
            "|---|---:|---:|---|---|---|",
        ]
        for c in rows:
            ev = c.get("measured") or ""
            ft = c.get("failure_type") or ""
            rs = c.get("responsibility") or ""
            lines.append(
                f"| {c.get('id')} | {str(c.get('pass'))} | {c.get('weight', 0)} | {ft} | {rs} | {ev} |"
            )
        return "\n".join(lines)


    quality_md = []
    quality_md.append("# Quality Analysis (Derived from logs/result.json)")
    quality_md.append(f"- GeneratedAt: {result.get('generated_at')}")
    quality_md.append(f"- Score: {summary.get('score')} | Grade: {summary.get('grade')} | OverallPass: {summary.get('overall_pass')}")
    quality_md.append("")
    quality_md.append("## Checks")
    quality_md.append(_md_table(chs) if chs else "- (No checks found in result.json.characteristics)")

    with open(out_quality_md, "w", encoding="utf-8") as f:
        f.write("\n".join(quality_md))

    final_md = []
    final_md.append("# [최종 품질 통합 보고서]")
    final_md.append("")
    final_md.append("## 1. 정적 분석 요약 (에이전트 1 결과)")
    final_md.append(_md_table(chs) if chs else "- (정적 분석 결과가 result.json에 반영되지 않았습니다.)")
    final_md.append("")
    final_md.append("## 2. 동적 테스트 결과 요약")
    # _parse_pytest_counts를 통해 stdout 원문에서 (3 passed, 1 failed) 같은 숫자를 추출합니다.
    counts = _parse_pytest_counts(stdout_text) 
    final_md.append(f"- **직접 실행 상태:** {'성공' if (run.get('exit_code') == 0) else '실패'}")
    final_md.append(f"- **테스트 성공 개수:** {counts.get('passed')} / **실패 개수:** {counts.get('failed')}")
    final_md.append("")
    final_md.append("## 3. pytest 실행 증명 로그 (원문)")
    final_md.append("```text") # 형식을 지정해주면 더 깔끔합니다.
    if stdout_text:
        final_md.append(stdout_text.strip())
    else:
        final_md.append("실행 로그 데이터가 없습니다.")
    final_md.append("```") # 여기서 한 번만 닫아주면 됩니다.
    final_md.append("")

    final_md.append("## 4. 상세 실패 원인 및 기술 분석")
    if failing:
        for c in failing:
            final_md.append(f"- **{c.get('id')}**: {c.get('measured')}")
    else:
        final_md.append("- 발견된 주요 결함 없음 (모든 항목 Pass)")
    final_md.append("")
    final_md.append("## 5. 종합 판정 및 개선 권고")
    final_md.append(f"- **최종 품질 등급:** {summary.get('grade')}")
    final_md.append(f"- **종합 판정:** {'Pass' if summary.get('overall_pass') else 'Fail'}")
    if failing:
        final_md.append("- **우선 개선 권고 사항:**")
        for c in failing[:2]:
            final_md.append(f"  - {c.get('id')}: {c.get('measured')}")
    else:
        final_md.append("- **우선 개선 권고 사항:** 없음")

    with open(out_final_md, "w", encoding="utf-8") as f:
        f.write("\n".join(final_md))

def build_result_json(
    spec: dict,
    static_json_paths: list,
    run_json_paths: list,
    out_result_json_path: str,
    out_quality_md_path: str,
    out_final_md_path: str,
    target_dir: str = None,
) -> dict:
    _ensure_dir(os.path.dirname(out_result_json_path))

    static_data, static_src = _load_json_if_exists(*static_json_paths)
    run_data, run_src = _load_json_if_exists(*run_json_paths)

    # static_data expected: list[dict]
    if static_data is None:
        static_list = []
        warnings = [f"static_analysis.json not found. searched={static_json_paths}"]
    else:
        static_list = static_data if isinstance(static_data, list) else []
        warnings = []

    if run_data is None:
        run_data = {"exit_code": 1, "stdout": "", "result_json_exists": False}
        warnings.append(f"run_artifacts.json not found. searched={run_json_paths}")

    spec_checks = (spec or {}).get("checks") or []
    grading = (spec or {}).get("grading") or {}

    characteristics = _normalize_static_to_characteristics(static_list, spec_checks)
    characteristics += _normalize_run_to_characteristics(run_data, spec_checks)
    characteristics = [classify_failure(c, run_data, (spec or {}).get("domain") or "") for c in characteristics]
    characteristics = dedupe_characteristics(characteristics)

    summary = _compute_summary(characteristics, grading)

    result = {
        "standard": "ISO/IEC 25010",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target_dir": target_dir,
        "spec": spec,
        "run": run_data,
        "characteristics": characteristics,
        "summary": summary,
        "warnings": warnings,
        "sources": {"static": static_src, "run": run_src},
    }

    with open(out_result_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        

    render_md_reports(result, out_quality_md_path, out_final_md_path)
    return result

def _original_game_description(project_type: str, target_dir: str, test_file_abs: str) -> str:
    return f"""
You are a QA agent for a Pygame-based game project.

Target project directory:
{target_dir}

Write the pytest file to:
{test_file_abs}

ABSOLUTE RULES:
- Use ONLY Python standard library + pytest
- Do NOT import project-local modules
- MUST use tests/_harness.py only:
  resolve_target_dir, resolve_file, read_text_file, run_command, summarize_exception
- The test must be robust across different entrypoint names (not only main.py).

HARNESS RULES (MANDATORY):
- You MUST use tests/_harness.py only. Do NOT use subprocess/open directly.
- Import MUST include (exact names):
  resolve_target_dir, resolve_file, read_text_file,
  run_command3, find_pygame_entrypoint,
  summarize_exception

ENTRYPOINT DISCOVERY (MANDATORY):
- You MUST locate the runnable entry script using:
  entry = find_pygame_entrypoint(resolve_target_dir())
- Do NOT hardcode "main.py" or any fixed filename.

RUNTIME RULE (MANDATORY):
- Execute only via:
  exit_code, stdout, stderr = run_command3(["python", str(entry)], cwd=TARGET_DIR, timeout_sec=5)
- Treat exit_code == 0 OR exit_code == 124 as PASS (124 is timeout; infinite loop is acceptable)
- However, if stderr contains "Traceback" / "Error" keywords, it is FAIL.

OUTPUT:
- Exactly one pytest file
- No markdown
- Pure Python code only
"""


def flatten_result_to_kv(result: dict) -> dict:
    kv = {}

    # meta
    kv["standard"] = result.get("standard")
    kv["generated_at"] = result.get("generated_at")
    kv["target_dir"] = result.get("target_dir")

    # summary
    summary = result.get("summary") or {}
    kv["summary.score"] = summary.get("score")
    kv["summary.grade"] = summary.get("grade")
    kv["summary.overall_pass"] = summary.get("overall_pass")
    kv["summary.passed_weight"] = summary.get("passed_weight")
    kv["summary.total_weight"] = summary.get("total_weight")

    # checks
    chs = result.get("characteristics") or []
    for ch in chs:
        cid = ch.get("id")
        if not cid:
            continue

        kv[f"{cid}.pass"] = ch.get("pass")
        kv[f"{cid}.weight"] = ch.get("weight")
        kv[f"{cid}.rule"] = ch.get("rule")
        kv[f"{cid}.method"] = ch.get("method")
        kv[f"{cid}.failure_type"] = ch.get("failure_type")
        kv[f"{cid}.responsibility"] = ch.get("responsibility")
        kv[f"{cid}.failure_reason"] = ch.get("failure_reason")


        measured = ch.get("measured")
        if isinstance(measured, dict):
            for k, v in measured.items():
                kv[f"{cid}.measured.{k}"] = v
        else:
            kv[f"{cid}.measured"] = measured

        # evidence (너는 지금 measured에 "file=... evidence=..."로 넣고 있어서 이것도 같이 저장)
        ev = ch.get("evidence")
        if isinstance(ev, dict):
            for k, v in ev.items():
                kv[f"{cid}.evidence.{k}"] = v
        elif ev is not None:
            kv[f"{cid}.evidence"] = ev

    # run_log
    run = result.get("run_log") or result.get("run") or {}
    kv["run.exit_code"] = run.get("exit_code")
    kv["run.stdout"] = run.get("stdout")
    kv["run.stderr"] = run.get("stderr")

    return kv


def _render_reports_from_result(result_json_path: str, quality_md_path: str, final_md_path: str) -> None:
    if not os.path.exists(result_json_path):
        return
    data = json.loads(open(result_json_path, "r", encoding="utf-8").read())
    checks = data.get("characteristics", [])
    summary = data.get("summary", {})

    lines = []
    lines.append("# Quality Analysis (Derived from result.json)")
    lines.append("")
    lines.append(f"- GeneratedAt: {data.get('generated_at')}")
    lines.append(f"- Score: {summary.get('score')} | Grade: {summary.get('grade')} | OverallPass: {summary.get('overall_pass')}")
    lines.append("")
    lines.append("## Checks")
    for c in checks:
        lines.append("")
        lines.append(f"### {c.get('id')} ({'Pass' if c.get('pass') else 'Fail'})")
        lines.append(f"- Metric: {c.get('metric')}")
        lines.append(f"- Rule: {c.get('rule')}")
        lines.append(f"- Measured: `{json.dumps(c.get('measured'), ensure_ascii=False)}`")
        ev = c.get("evidence", [])
        if ev:
            lines.append("- Evidence:")
            for e in ev[:10]:
                lines.append(f"  - {e.get('file')}:{e.get('line_start')}~{e.get('line_end')} {e.get('note')}")
            if len(ev) > 10:
                lines.append(f"  - ... ({len(ev) - 10} more)")

    _ensure_dir(os.path.dirname(quality_md_path))
    open(quality_md_path, "w", encoding="utf-8").write("\n".join(lines))

    final_lines = []
    final_lines.append("# Final Test Report (Derived from result.json)")
    final_lines.append("")
    final_lines.append(f"- Grade: {summary.get('grade')}")
    final_lines.append(f"- Score: {summary.get('score')}")
    final_lines.append(f"- OverallPass: {summary.get('overall_pass')}")
    final_lines.append("")
    final_lines.append("## Failing Checks")
    fails = [c for c in checks if not c.get("pass")]
    if not fails:
        final_lines.append("- None")
    else:
        for c in fails:
            final_lines.append(f"- {c.get('id')}: rule={c.get('rule')} measured={json.dumps(c.get('measured'), ensure_ascii=False)}")
    _ensure_dir(os.path.dirname(final_md_path))
    open(final_md_path, "w", encoding="utf-8").write("\n".join(final_lines))

def sanitize_generated_test_file(path: str) -> None:
    if not os.path.exists(path):
        return

    raw = open(path, "r", encoding="utf-8").read()
    raw = raw.lstrip("\ufeff").strip()

    # code fence 제거
    raw = raw.replace("```python", "").replace("```", "").strip()

    # JSON으로 감싸진 경우만 풀기
    try:
        obj = json.loads(raw)
        if isinstance(obj, str):
            raw = obj
        elif isinstance(obj, dict):
            for k in ("code", "content", "text", "source"):
                if isinstance(obj.get(k), str):
                    raw = obj[k]
                    break
    except Exception:
        pass

    # 이스케이프 복원(한 줄짜리 문자열인 경우)
    is_single_line = ("\n" not in raw)
    looks_escaped = ("\\n" in raw or "\\r\\n" in raw)
    if is_single_line and looks_escaped:
        raw = raw.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")

    raw = raw.replace('\\"', '"')
    raw = re.sub(r"\\[ \t]+\n", "\\\n", raw)
    raw = re.sub(r",\s*\\\n", "\n", raw)

    # (중요) 1순위: 하네스 임포트 라인부터 자르기
    m = re.search(r"^from\s+tests\._harness\s+import\s*\(", raw, flags=re.MULTILINE)
    if m:
        raw = raw[m.start():].lstrip()
    else:
        # 2순위: 일반 import/from
        m2 = re.search(r"^(?:from\s+\S+\s+import\s+|import\s+\S+)", raw, flags=re.MULTILINE)
        if not m2:
            raise RuntimeError(f"Invalid generated test file (no import/from found): {path}")
        raw = raw[m2.start():].lstrip()

    # BASE_DIR 같은 찌꺼기 제거(필요 시)
    raw = re.sub(r"^BASE_DIR\s*=\s*resolve_target_dir\(\)\s*\n+", "", raw, flags=re.MULTILINE)

    with open(path, "w", encoding="utf-8") as f:
        f.write(raw.rstrip() + "\n")


def validate_python_syntax(file_path: str) -> None:
    import py_compile
    py_compile.compile(file_path, doraise=True)


def patch_generated_test_file_for_darkhttpd(path: str) -> None:
    # NOTE:
    # 기존 구현은 server_root/wait_for_port 등 하네스 밖 코드를 주입하면서
    # 들여쓰기/괄호 깨짐(IndentationError)을 자주 유발했다.
    # 현재 파이프라인은 tests/_harness(wait_for_tcp, http_get_raw 등)로 통일하므로
    # darkhttpd 전용 패치는 사용하지 않는다.
    return

def strip_stray_harness_fragment(test_file_abs: str) -> None:
    text = Path(test_file_abs).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    cleaned = []
    i = 0
    n = len(lines)

    while i < n:
        ln = lines[i]

        # stray fragment 시작 패턴: "resolve_target_dir, run_command, ..." 같이 콤마로 끝나는 라인
        if ln.strip().startswith("resolve_target_dir,") and ln.rstrip().endswith(","):
            # 이 블록은 다음에 들여쓰기 라인 + ")"로 끝나는 경우가 많아서 통째로 스킵
            i += 1
            while i < n:
                s = lines[i].strip()
                # 빈 줄 포함해서, ')'로 끝나는 라인을 만나면 종료
                if s == ")" or s.endswith(")"):
                    i += 1
                    break
                i += 1
            continue

        cleaned.append(ln)
        i += 1

    Path(test_file_abs).write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")


# ... 기존 헬퍼 함수들 (_ensure_dir, _load_json_if_exists 등) ...

def build_and_render_final_reports(project_type: str, target_dir: str, paths: dict):
    _ensure_dir(paths["LOGS_DIR"])

    static_data = []
    run_data = {}

    _sd, _ = _load_json_if_exists(paths["STATIC_JSON_PATH"])
    _rd, _ = _load_json_if_exists(paths["RUN_ARTIFACTS_PATH"])

    if isinstance(_sd, list):
        static_data = _sd
    elif isinstance(_sd, dict):
        static_data = [_sd]
    else:
        static_data = []

    if isinstance(_rd, dict):
        run_data = _rd
    else:
        run_data = {}

    if not static_data:
        print("경고: 정적 분석 데이터를 찾을 수 없습니다.")
        return

    # 기존 flappy 가드는 “단일 타겟”에서만 의미가 커서, 멀티타겟에서는 오탐 가능.
    # 지금은 일단 제거(또는 필요하면 target_dir 기반으로 더 안전하게 바꾸기).
    # evidence_text = " ".join([(x.get("data_evidence") or "") for x in static_data if isinstance(x, dict)])
    # if "flappy" in evidence_text.lower(): ...

    spec_key = map_project_type_to_spec_key(project_type)
    spec = get_quality_spec(spec_key)

    actual_spec = spec.get("spec") if isinstance(spec, dict) and "spec" in spec else spec

    if isinstance(actual_spec, list):
        actual_spec = {
            "domain": spec_key,
            "checks": actual_spec,
            "grading": {},
        }
    elif not isinstance( actual_spec, dict):
        actual_spec = {
            "domain": spec_key,
            "checks": [],
            "grading": {},
        }

    characteristics = _normalize_static_to_characteristics(static_data, actual_spec.get("checks", []))
    characteristics += _normalize_run_to_characteristics(run_data or {}, actual_spec.get("checks", []))
    characteristics = [classify_failure(c, run_data or {}, spec_key) for c in characteristics]

    summary = _compute_summary(characteristics, actual_spec.get("grading", {}))

    result = {
        "standard": "ISO/IEC 25010",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "characteristics": characteristics,
        "run_log": run_data,
        "target_dir": target_dir,
    }

    with open(paths["RESULT_JSON_PATH"], "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    kv = flatten_result_to_kv(result)
    with open(paths["RESULT_KV_JSON_PATH"], "w", encoding="utf-8") as f:
        json.dump(kv, f, ensure_ascii=False, indent=2)

    render_md_reports(result, paths["QUALITY_MD_PATH"], paths["FINAL_MD_PATH"])


if __name__ == "__main__":
    print("### [AI QA Team] 품질 분석 및 자동화 테스트 시작 ###")

    targets = iter_target_dirs(TARGET_ROOT)
    if not targets:
        raise RuntimeError(f"No target directories found under: {TARGET_ROOT}")

    for t in targets:
        target_dir = str(t)
        project_type = detect_project_type(target_dir)
        paths = make_paths(target_dir)

        print(f"\n--- TARGET: {paths['TARGET_NAME']} | DOMAIN: {project_type} ---")

        try:
            _ensure_dir(paths["LOGS_DIR"])

            crew = build_crew_for_target(project_type, target_dir, paths)
            crew.kickoff()

            if not os.path.exists(paths["TEST_FILE_ABS"]):
                print(f"[ERROR] test file not generated: {paths['TEST_FILE_ABS']}")
                print("[DEBUG] target dir files:")
                for p in Path(target_dir).glob("*"):
                    print(" -", p.name)
                raise RuntimeError(f"Test file not generated: {paths['TEST_FILE_ABS']}")

            # 1. 하네스 파일 존재 보장
            ensure_harness_exists(target_dir)

            # 2. 코드 정제 (백틱 제거 등)를 먼저 수행하여 깨끗한 상태로 만듦
            sanitize_generated_test_file(paths["TEST_FILE_ABS"])
            force_trim_test_to_harness_import(paths["TEST_FILE_ABS"])
            strip_stray_harness_fragment(paths["TEST_FILE_ABS"])
            # 3. 정제된 코드 위에 하네스 임포트 및 BASE_DIR 선언을 강제로 덮어씀 (순서 변경)
            raw_test_code = open(paths["TEST_FILE_ABS"], "r", encoding="utf-8").read()
            patched_test_code = enforce_harness_import(raw_test_code)
            with open(paths["TEST_FILE_ABS"], "w", encoding="utf-8") as f:
                f.write(patched_test_code)

            # 4. C 프로젝트인 경우 추가 패치 실행 (선택 사항)
            if project_type == "c_http_server":
                patch_generated_test_file_for_darkhttpd(paths["TEST_FILE_ABS"])

            # 5. 최종 문법 및 하네스 준수 여부 검증
            validate_python_syntax(paths["TEST_FILE_ABS"])
            validate_harness_compliance(paths["TEST_FILE_ABS"])

            print("\n### 에이전트 작업 완료. 최종 통합 보고서 생성 중...")
            build_and_render_final_reports(project_type, target_dir, paths)

            print("\n### 완료 ###")
            print(f"- 최종 데이터: {paths['RESULT_JSON_PATH']}")
            print(f"- 통합 보고서: {paths['FINAL_MD_PATH']}")
            print(f"- KV 데이터: {paths['RESULT_KV_JSON_PATH']}")

        except Exception as e:
            print(f"\n[FAIL] {paths['TARGET_NAME']} 시스템 에러 발생: {e}")