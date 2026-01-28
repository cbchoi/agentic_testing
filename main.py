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

PROJECT_TYPE = "c_http_server"  # "game" | "c_http_server"

TARGET_DIR = "target_apps/flappybird"

if PROJECT_TYPE == "c_http_server":
    TARGET_DIR = "target_apps/Tinyhttpd"
    # TARGET_DIR = "target_apps/Tinyhttpd"

TEST_FILE_REL = "test_quality_check.py"
TEST_FILE_ABS = str(Path(TARGET_DIR).joinpath(TEST_FILE_REL))

# All generated artifacts (JSON + MD) are fixed to this directory.
LOGS_DIR = "logs"
STATIC_JSON_PATH = os.path.join(LOGS_DIR, "static_analysis.json")
RUN_ARTIFACTS_PATH = os.path.join(LOGS_DIR, "run_artifacts.json")
RESULT_JSON_PATH = os.path.join(LOGS_DIR, "result.json")
QUALITY_MD_PATH = os.path.join(LOGS_DIR, "quality_analysis_report.md")
FINAL_MD_PATH = os.path.join(LOGS_DIR, "final_tc_report.md")
RESULT_KV_JSON_PATH = os.path.join(LOGS_DIR, "result_kv.json")

# ----------------------------------------------------------------
# 1. Agents 설정: 페르소나와 전문성 강화
# ----------------------------------------------------------------

analyzer = Agent(
    role="ISO/IEC 25010 품질 인증 심사원",
    goal=f"대상 프로젝트 소스코드를 정밀 분석하여 품질 표준 만족 여부를 증명하라: {get_quality_prompt(PROJECT_TYPE)}",
    backstory=(
        "너는 소프트웨어 품질 국제 표준 전문가야. 주관적인 판단을 배제하고 오직 코드 데이터로만 말한다.\n"
        "독해를 통해 함수의 라인 수, 복잡도, 예외 처리 위치를 정확히 찾아내며,\n"
        "특히 변수(예: fps)가 사용된 경우 해당 변수의 실제 할당값을 역추적하여 수치화한다."
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[
    ListFilesTool(allowed_root=TARGET_DIR),
    ReadFileTool(allowed_root=TARGET_DIR),
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
    ),
    llm="gpt-4o-mini",
    verbose=True,
    allow_delegation=False,
    tools=[ListFilesTool(allowed_root=TARGET_DIR), ReadFileTool(allowed_root=TARGET_DIR), WriteFileTool()],
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
    tools=[
    ListFilesTool(allowed_root=TARGET_DIR),
    ReadFileTool(allowed_root=TARGET_DIR),
    WriteFileTool(),
    RunPytestTool(),
    ],
    config={"temperature": 0.0},
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
    return f"""
[분석 대상 강제]
- 반드시 첫 번째 행동으로 list_files tool을 호출한다.
- list_files 호출 인자:
  directory_path = "{target_dir}"
- 너는 반드시 "{target_dir}" 디렉토리 하위의 파일만 분석해야 한다.
- "{target_dir}" 밖의 파일은 절대 읽지 말고, 언급하지 말고, 근거로 사용하지 마라.

[출력 포맷 안전 규칙 - 매우 중요]
- JSON 문자열에 역슬래시(\\)를 절대 포함하지 마라.
- 파일 경로를 언급해야 한다면 반드시 아래 중 하나만 사용하라:
  1) 파일명만
  2) 슬래시(/) 기반 상대경로
- 인사를 하거나 설명을 붙이지 마라. 오직 순수 JSON 배열만 출력하라.

[반드시 사용해야 할 항목 ID (id 필드에 아래 값만 사용)]
1. Maintainability.FunctionLOC
2. Maintainability.MainLoopComplexity
3. PerformanceEfficiency.TimeBehaviour
4. Reliability.FaultTolerance.ResourceLoading
5. FunctionalSuitability.StateTransitionValidation.ExitSignals

[출력 JSON 스키마 (필수)]
각 배열 원소는 다음 키를 반드시 포함해야 한다:
{{
  "id": "위의 항목 ID 중 하나",
  "quality_feature": "해당 특성명",
  "decision_rule": "적용된 수치 기준",
  "measurement_method": "측정 방식",
  "measured": "실측 수치",
  "final_judgment": "Pass 또는 Fail",
  "data_evidence": "근거 텍스트"
}}
"""

github_analysis_task = Task(
    description=_analysis_task_description(PROJECT_TYPE, TARGET_DIR),
    expected_output="static_analysis.json 형식의 JSON 배열",
    agent=analyzer,
    output_file=STATIC_JSON_PATH,
)

def _test_generation_description(project_type: str, target_dir: str, test_file_abs: str) -> str:
    if project_type == "c_http_server":
        return f"""
[최우선 규칙]
- 이 작업의 성공 기준은 “pytest가 문법 오류 없이 실행 가능한 테스트 파일 생성”이다.
- 테스트 코드는 반드시 ‘실제 파이썬 소스 코드’ 형태여야 하며, \\n 같은 이스케이프 문자열 형태로 출력하면 실패다.

[목표]
- darkhttpd를 WSL(Ubuntu)에서 실행하고, pytest로 HTTP 기본 동작을 검증하는 테스트 파일을 생성하라.
- 생성 경로: '{test_file_abs}'

[중요 제약 - 위반 금지]
- 외부 라이브러리(requests 등) 사용 금지. 표준 라이브러리만 사용하라.
- Windows 경로를 WSL bash에서 직접 cd 하지 마라. (예: cd C:\\... 금지)
- 반드시 아래 방식으로만 WSL 경로를 얻어 cd 해야 한다:
- wsl wslpath -a "<windows_abs_path>" 로 변환 후 cd
- 서버 실행은 반드시 "wsl bash -lc <command>" 형태로만 실행하라.

[필수 구현 요구]
- os.chdir()는 절대 WSL 경로에 사용하지 마라. Windows Python에서는 Windows 경로만 사용 가능하다.
- WSL 경로는 오직 "wsl bash -lc 'cd <wsl_path> && ...'" 내부에서만 사용하라.
- 테스트 파일 내부에서 다음을 구현하라:
1) Windows의 target_dir 절대경로를 구한다 (Path/resolve 사용)
2) wslpath로 WSL 경로로 변환한다 (subprocess.run(["wsl","wslpath","-a", win_path], ...))
3) 아래 WSL 커맨드로 서버를 백그라운드로 띄운다 (subprocess.Popen 권장)
    - cd "<wsl_dir>"
    - make
    - ./httpd 8080
4) 소켓으로 GET 요청을 보내 status line을 읽어 검증한다.
5) 테스트 종료 시 서버 프로세스를 반드시 종료한다.
- os.chdir()는 절대 WSL 경로에 사용하지 마라. Windows Python에서는 Windows 경로만 사용 가능하다.
- WSL 경로는 오직 "wsl bash -lc 'cd <wsl_path> && ...'" 내부에서만 사용하라.

[테스트 케이스]
1) GET /index.html 응답의 status line에 "200" 또는 "304"가 포함되어야 한다.
2) GET /nope-404.html 응답의 status line에 "404"가 포함되어야 한다.

[추가 지시]
- 테스트 파일 상단에 target_dir을 하드코딩하지 말고, 반드시 테스트 파일 위치 기준으로 상대경로로 계산하라.
    예: Path(__file__).resolve().parent 가 target_dir임

[출력 강제 규칙 - 위반 시 실패]
- 출력은 순수 파이썬 코드만 포함해야 한다. 설명 문장/마크다운/문서 문자열(docstring) 금지.
- 출력에 백슬래시(\\) 문자를 절대 포함하지 마라. (예: \\n, \\t, \\r, \\\\n, \\\\r\\\\n 등 금지)
- JSON(dict/array) 또는 따옴표로 감싼 “문자열”로 감싸서 출력하지 마라. (예: {{\"code\": \"...\"}} / \"....\" 금지)
- 줄바꿈은 반드시 “실제 줄바꿈”으로만 표현하라. 문자열 "\\n" 형태로 표현하면 실패다.
- 파일 첫 줄은 반드시 import 또는 from 으로 시작해야 한다.
- 다음 문자열을 절대 포함하지 마라: ``` , ''' , \""" , ```python
- 반드시 아래 테스트 함수 2개를 정의하라:
- def test_index_returns_200_or_304():
- def test_missing_returns_404():
- 반드시 write_file 도구로 파일을 저장하라. (출력만 하고 끝내면 실패)
- 출력에 \n 같은 이스케이프 문자열을 절대 만들지 마라. 줄바꿈은 실제 줄바꿈으로만 표현하라.
    """

test_generation_task = Task(
    description=_test_generation_description(PROJECT_TYPE, TARGET_DIR, TEST_FILE_ABS),
    expected_output="pytest 테스트 코드 파일 생성 (순수 파이썬 코드)",
    agent=test_creator,
    output_file=TEST_FILE_ABS,
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

   write_file 입력 형식: "{TEST_FILE_ABS}|<정제된 파이썬 코드 전체>"

1) RunPytestTool을 다음 입력으로 실행하라:
   "{TARGET_DIR}|{TEST_FILE_REL} -q"

2) 실행 결과를 JSON으로 저장하라 (exit_code, stdout).
""",
    expected_output="JSON object containing exit_code and stdout.",
    agent=test_reporter,
    context=[github_analysis_task, test_generation_task],
    output_file=RUN_ARTIFACTS_PATH,
)

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _load_json_lenient_from_text(text: str):
    """
    텍스트에서 '첫 번째 JSON 값(객체/배열)'만 파싱한다.
    에이전트가 JSON 뒤에 설명/로그를 붙여도 죽지 않게 하기 위함.
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

    # 첫 JSON 시작 위치 찾기
    m = re.search(r"[\{\[]", text)
    if not m:
        return None

    text = text[m.start():].lstrip()

    decoder = json.JSONDecoder()
    obj, _idx = decoder.raw_decode(text)  # 첫 JSON만 파싱
    return obj


def _load_json_if_exists(*paths: str):
    for p in paths:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()

            # 엄격 파싱 먼저 시도
            try:
                return json.loads(raw), p
            except Exception:
                # 실패하면 관대한 파싱(첫 JSON만)
                data = _load_json_lenient_from_text(raw)
                return data, p

    return None, None


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

        is_pass = (failed == 0 and passed >= 1)

        out.append(
            {
                "id": cid,
                "metric": metric,
                "measured": {"passed": passed, "failed": failed, "skipped": skipped},
                "pass": bool(is_pass),
                "evidence": {
                    "pytest_counts": counts,
                    "stdout_tail": stdout_text[-2000:],
                },
            }
        )

    return out


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
        lines = ["| Check ID | Pass | Weight | Evidence |", "|---|---:|---:|---|"]
        for c in rows:
            ev = c.get("measured") or ""
            lines.append(f"| {c.get('id')} | {str(c.get('pass'))} | {c.get('weight', 0)} | {ev} |")
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

    # 1) JSON으로 감싸진 경우만 풀기
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

    # 2) 핵심: "한 줄짜리" 이스케이프 문자열일 때만 복원
    is_single_line = ("\n" not in raw)
    looks_escaped = ("\\n" in raw or "\\r\\n" in raw)

    if is_single_line and looks_escaped:
        # 이 경우만 unicode_escape 사용
        raw = raw.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")

    # 3) import/from 시작 위치 찾기
    m = re.search(r"^(?:from\s+\S+\s+import\s+|import\s+\S+)", raw, flags=re.MULTILINE)
    if not m:
        raise RuntimeError(f"Invalid generated test file (no import/from found): {path}")

    raw = raw[m.start():].lstrip()

    # 4) 삼중 따옴표 제거 (맨 앞에 있을 때만)
    if raw.startswith("'''") or raw.startswith('"""'):
        q = "'''" if raw.startswith("'''") else '"""'
        end = raw.find(q, 3)
        if end != -1:
            raw = raw[end + 3 :].lstrip()

    with open(path, "w", encoding="utf-8") as f:
        f.write(raw.rstrip() + "\n")


    open(path, "w", encoding="utf-8").write(raw.rstrip() + "\n")

def validate_python_syntax(file_path: str) -> None:
    import py_compile
    py_compile.compile(file_path, doraise=True)


def patch_generated_test_file_for_darkhttpd(path: str) -> None:
    if not os.path.exists(path):
        raise RuntimeError(f"Test file not found to patch: {path}")

    src = open(path, "r", encoding="utf-8").read()

    # (A) pathlib import / server_root 강제
    if "from pathlib import Path" not in src:
        # import 블록 맨 위에 추가
        src = "from pathlib import Path\n" + src

    if "server_root =" not in src:
        # pathlib import 다음에 삽입
        src = src.replace(
            "from pathlib import Path\n",
            "from pathlib import Path\n\nserver_root = Path(__file__).resolve().parent\n",
            1,
        )
    else:
        # 기존 server_root 정의가 있으면 강제로 교체
        src = re.sub(
            r"^server_root\s*=.*$",
            "server_root = Path(__file__).resolve().parent",
            src,
            flags=re.MULTILINE,
        )

    # (B) wait_for_port 없으면 삽입
    if "def wait_for_port" not in src:
        helper = """
def wait_for_port(host: str, port: int, timeout_sec: float = 5.0) -> bool:
    import time
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False
""".lstrip("\n")

        m = re.search(r"^def\s+start_server\s*\(", src, flags=re.MULTILINE)
        if m:
            src = src[:m.start()] + helper + "\n\n" + src[m.start():]
        else:
            # start_server가 없으면 어차피 테스트가 불안정 -> 그냥 맨 위에라도 추가
            src = helper + "\n\n" + src

    # (C) start_server 내부 커맨드에서 cd 경로를 server_root 기반으로 강제
    # - wsl_dir 같은 변수가 있든 없든, "server_root"를 쓰도록 유도
    # - 가장 안전: wsl_dir 계산을 server_root 기준으로 강제하는 코드가 있으면 교체
    src = re.sub(
        r"Path\(__file__\)\.resolve\(\)\.parent",
        "server_root",
        src,
    )

    # (D) 서버 실행 후 포트 대기 강제 (8080)
    if "wait_for_port(" not in src:
        # 가장 흔한 패턴: 서버 실행 라인(./darkhttpd ...) 뒤에 assert 삽입
        src = re.sub(
            r"(\./darkhttpd[^\n]*\n)",
            r"\1    assert wait_for_port('127.0.0.1', 8080, 5.0), 'Server did not start'\n",
            src,
            count=1,
        )

    open(path, "w", encoding="utf-8").write(src)


# ----------------------------------------------------------------
# 3. Crew & Execution
# ----------------------------------------------------------------

qa_crew = Crew(
    agents=[analyzer, test_creator, test_reporter],
    tasks=[github_analysis_task, test_generation_task, test_execution_task],
    process=Process.sequential,
)

# ... 기존 헬퍼 함수들 (_ensure_dir, _load_json_if_exists 등) ...

def build_and_render_final_reports():
    """
    에이전트들이 생성한 조각 데이터들을 모아 
    최종 result.json을 만들고 마크다운을 렌더링합니다.
    """
    _ensure_dir(LOGS_DIR)

    # 1. 데이터 로드 (기본값 먼저)
    static_data = []
    run_data = {}

    _sd, _ = _load_json_if_exists(STATIC_JSON_PATH)
    _rd, _ = _load_json_if_exists(RUN_ARTIFACTS_PATH)

    # ---- normalize loaded json types ----
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
    # -------------------------------------

    if not static_data:
        print("경고: 정적 분석 데이터를 찾을 수 없습니다.")
        return

    # --- target guard: flappy 등 다른 게임 분석이면 즉시 중단 ---
    evidence_text = " ".join([(x.get("data_evidence") or "") for x in static_data if isinstance(x, dict)])
    if "flappy" in evidence_text.lower():
        raise RuntimeError(
            f"Static analysis target mismatch: expected {TARGET_DIR} but evidence mentions 'flappy', 'breakout'. "
            "ListFilesTool 범위가 전체로 잡힌 상태입니다."
        )
    # ------------------------------------------------------------

    # 2. ISO spec 기준에 맞춘 데이터 정규화 및 점수 계산
    spec = get_quality_spec(PROJECT_TYPE)
    actual_spec = spec.get("spec") if isinstance(spec, dict) and "spec" in spec else spec

    characteristics = _normalize_static_to_characteristics(static_data, actual_spec.get("checks", []))
    characteristics += _normalize_run_to_characteristics(run_data or {}, actual_spec.get("checks", []))
    summary = _compute_summary(characteristics, actual_spec.get("grading", {}))

    # 3. 통합 result.json 생성
    result = {
        "standard": "ISO/IEC 25010",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "characteristics": characteristics,
        "run_log": run_data,
    }

    with open(RESULT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    kv = flatten_result_to_kv(result)
    with open(RESULT_KV_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(kv, f, ensure_ascii=False, indent=2)

    # 4. 최종 마크다운 렌더링 호출
    render_md_reports(result, QUALITY_MD_PATH, FINAL_MD_PATH)


if __name__ == "__main__":
    print("### [AI QA Team] 품질 분석 및 자동화 테스트 시작 ###")
    try:
        _ensure_dir(LOGS_DIR)
        
        # 1. 에이전트 작업 시작 (파일 생성)
        qa_crew.kickoff()
        if not os.path.exists(TEST_FILE_ABS):
            # 생성 실패 원인 파악을 위해 디렉토리 목록 출력
            print(f"[ERROR] test file not generated: {TEST_FILE_ABS}")
            print("[DEBUG] target dir files:")
            for p in Path(TARGET_DIR).glob("*"):
                print(" -", p.name)
            raise RuntimeError(f"Test file not generated: {TEST_FILE_ABS}")

        
        # 생성된 테스트 파일은 매번 정제 + 패치해서 안정적으로 통과 형태로 강제
        sanitize_generated_test_file(TEST_FILE_ABS)
        patch_generated_test_file_for_darkhttpd(TEST_FILE_ABS)
        validate_python_syntax(TEST_FILE_ABS)

        if not os.path.exists(TEST_FILE_ABS):
            raise RuntimeError(f"Test file not generated: {TEST_FILE_ABS}")

        # 2. 작업 완료 후 데이터 통합 및 리포트 생성 (여기가 호출 위치!)
        print("\n### 에이전트 작업 완료. 최종 통합 보고서 생성 중...")
        build_and_render_final_reports()

        print("\n### 모든 공정이 완료되었습니다!")
        print(f"- 최종 데이터: {RESULT_JSON_PATH}")
        print(f"- 통합 보고서: {FINAL_MD_PATH}")
        print(f"- KV 데이터: {RESULT_KV_JSON_PATH}")


    except Exception as e:
        print(f"\n시스템 에러 발생: {e}")
