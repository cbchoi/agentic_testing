# [최종 품질 통합 보고서]

## 1. 정적 분석 요약 (에이전트 1 결과)
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| Maintainability.FunctionLOC | False | 0.25 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'accept_request' has 72 NLOC exceeding the limit. |
| Maintainability.MainLoopComplexity | False | 0.15 | SYSTEM_DEFECT | TARGET_SYSTEM | Function 'accept_request' has a cyclomatic complexity of 24 exceeding the limit. |
| Reliability.FaultTolerance.ResourceLoading | True | 0.2 |  |  | No warnings found in resource loading checks. |
| FunctionalSuitability.HttpBasic | False | 0.4 | SYSTEM_DEFECT | TARGET_SYSTEM | Will be evaluated by pytest execution output |
| TestExecution.PytestRun | False | 0.0 | SYSTEM_DEFECT | TARGET_SYSTEM | {'exit_code': 1} |
| FunctionalSuitability.HttpBasic | False | 0.4 | SYSTEM_DEFECT | TARGET_SYSTEM | {'passed': 0, 'failed': 1, 'skipped': 0} |

## 2. 동적 테스트 결과 요약
- **직접 실행 상태:** 실패
- **테스트 성공 개수:** 0 / **실패 개수:** 1

## 3. pytest 실행 증명 로그 (원문)
```text
F                                                                        [100%]
================================== FAILURES ===================================
___________________________ test_http_server_smoke ____________________________

    def test_http_server_smoke():
        run_command(['make'], cwd=TARGET_DIR)
>       server_handle = start_process(['./http_server'], cwd=TARGET_DIR)

tests\test_quality_check.py:12: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

cmd = ['./http_server'], cwd = None

    def start_process(cmd: Union[str, list[str]], cwd: Path | None = None) -> ProcessHandle:
        """
        Start a process robustly across targets (Windows + WSL + Linux).
    
        - darkhttpd: enforce '-p 8080' and ensure a wwwroot positional arg
        - tinyhttpd/httpd: enforce positional port '8080'
          * if cmd is './tinyhttpd' but actual binary is 'httpd' or 'httpd.exe', auto-fallback
          * force WSL execution (linux build/run assumption)
          * IMPORTANT: convert Windows exe path -> /mnt/... before wrapping WSL
        - Adds pre-clean for httpd(8080) to avoid "bind: Address already in use"
        - Stores last server handle so wait_for_tcp() can detect early exits and surface stderr
        """
        global _LAST_SERVER_HANDLE, _LAST_SERVER_EXE
    
        cwd = cwd or resolve_target_dir()
        orig_cwd = str(cwd)
    
        if isinstance(cmd, str):
            cmd_list = [cmd]
        else:
            cmd_list = list(cmd)
    
        cmd_list = [str(x) for x in cmd_list if str(x).strip()]
        if not cmd_list:
            raise RuntimeError("start_process: empty cmd")
    
        desired_port = "8080"
        wrapped = False
    
        def _set_flag_value(flag: str, value: str) -> None:
            if flag in cmd_list:
                i = cmd_list.index(flag)
                if i + 1 < len(cmd_list):
                    cmd_list[i + 1] = value
                else:
                    cmd_list.append(value)
            else:
                cmd_list.insert(1, flag)
                cmd_list.insert(2, value)
    
        def _force_positional_port(value: str) -> None:
            for i in range(1, len(cmd_list)):
                if str(cmd_list[i]).isdigit():
                    cmd_list[i] = value
                    return
            cmd_list.append(value)
    
        def _normalize_tinyhttpd_binary() -> None:
            exe_token = cmd_list[0]
            exe_path = Path(exe_token)
            name = exe_path.name.lower()
    
            if name not in ("tinyhttpd", "tinyhttpd.exe"):
                return
    
            candidates = ["httpd", "httpd.exe", "tinyhttpd", "tinyhttpd.exe"]
            for c in candidates:
                cand = cwd / c
                if cand.exists() and cand.is_file():
                    cmd_list[0] = str(cand.resolve())
                    return
    
        def _normalize_httpd_binary_to_absolute() -> None:
            exe_token = cmd_list[0]
            exe_path = Path(exe_token)
            name = exe_path.name.lower()
    
            if name not in ("httpd", "httpd.exe"):
                return
            if exe_path.is_absolute():
                return
    
            cand = cwd / name
            if cand.exists() and cand.is_file():
                cmd_list[0] = str(cand.resolve())
                return
    
            if name == "httpd":
                cand_exe = cwd / "httpd.exe"
                if cand_exe.exists() and cand_exe.is_file():
                    cmd_list[0] = str(cand_exe.resolve())
                    return
    
        # --- Target-specific normalization ---
        _normalize_tinyhttpd_binary()
        _normalize_httpd_binary_to_absolute()
    
        exe_name = Path(cmd_list[0]).name.lower()
    
        # --- Pre-clean for tinyhttpd/httpd: avoid "bind: Address already in use" (8080) ---
        # test_quality_check.py를 건드릴 수 없으니, 하네스가 실행 환경을 안정화한다.
        if exe_name in ("httpd", "httpd.exe", "tinyhttpd", "tinyhttpd.exe"):
            # pkill / fuser는 WSL/Linux에서만 의미가 있고, 없으면 그냥 무시한다.
            try:
                # 남아있는 httpd/tinyhttpd 종료
                run_command(
                    ["bash", "-lc", "pkill -f '(^|/)(httpd|tinyhttpd)(\\.exe)?($|\\s)' || true"],
                    cwd=cwd,
                    timeout_sec=2,
                )
            except Exception:
                pass
    
            try:
                # 8080 점유 프로세스 kill (fuser 존재 시)
                run_command(
                    ["bash", "-lc", "command -v fuser >/dev/null 2>&1 && fuser -k 8080/tcp || true"],
                    cwd=cwd,
                    timeout_sec=3,
                )
            except Exception:
                pass
        # -------------------------------------------------------------------------------
    
        # tinyhttpd/httpd: port enforcement first
        if exe_name in ("httpd", "httpd.exe", "tinyhttpd", "tinyhttpd.exe") or ("tinyhttpd" in exe_name):
            _force_positional_port(desired_port)
    
                # darkhttpd: -p 8080 + wwwroot
            if "darkhttpd" in exe_name:
                _set_flag_value("-p", desired_port)
    
                # config.ini 같은 설정 파일은 darkhttpd 실행 인자로 쓰지 않는다.
                # (darkhttpd는 기본적으로 "wwwroot" 포지셔널만 기대하는 편이라 즉시 종료할 수 있음)
                ini_like = [a for a in cmd_list[1:] if str(a).lower().endswith((".ini", ".conf"))]
                if ini_like:
                    for a in ini_like:
                        cmd_list.remove(a)
    
                # --port 같은 비표준 옵션이 섞이면 제거
                if "--port" in cmd_list:
                    i = cmd_list.index("--port")
                    del cmd_list[i : min(i + 2, len(cmd_list))]
    
                # wwwroot 확보: 없으면 ./www 있으면 그거, 없으면 "."
                positional = [a for a in cmd_list[1:] if not str(a).startswith("-")]
                if not positional:
                    base = Path(orig_cwd)
                    www = base / "www"
                    cmd_list.append("www" if www.exists() and www.is_dir() else ".")
    
    
        # --- Force WSL for tiny/httpd (Linux build/run assumption) ---
        if exe_name in ("httpd", "httpd.exe", "tinyhttpd", "tinyhttpd.exe"):
            head = str(cmd_list[0])
    
            # 1) Windows absolute path -> /mnt/... so bash can execute it
            if re.match(r"^[A-Za-z]:\\", head) or re.match(r"^[A-Za-z]:/", head):
                cmd_list[0] = _to_wsl_path(head)
            # 2) bare name -> ./name so it resolves in cwd inside WSL
            elif not head.startswith(("./", "/")):
                cmd_list[0] = "./" + head
    
            # 3) wrap with wsl --cd <cwd>
            cmd_list, _ = _wrap_wsl(cmd_list, cwd)
            cwd = None
            wrapped = True
        # -----------------------------------------------------------
    
        # --- Windows/WSL path handling (generic) ---
        if re.match(r"^[A-Za-z]:\\", cmd_list[0]) or re.match(r"^[A-Za-z]:/", cmd_list[0]):
            cmd_list[0] = _to_wsl_path(cmd_list[0])
    
        if cmd_list[0].startswith("/mnt/"):
            cmd_list, _ = _wrap_wsl(cmd_list, cwd)
            cwd = None
            wrapped = True
    
        if (not wrapped) and _should_use_wsl(cmd_list, cwd):
            cmd_list, _ = _wrap_wsl(cmd_list, cwd)
            cwd = None
            wrapped = True
    
        p = subprocess.Popen(
            cmd_list,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    
        # 1) truly-immediate exit guard
        time.sleep(0.2)
        if p.poll() is not None:
            try:
                out, err = p.communicate(timeout=1)
            except Exception:
                out, err = "", ""
>           raise RuntimeError(
                "start_process: process exited immediately\n"
                f"cmd={cmd_list}\n"
                f"stdout={out}\n"
                f"stderr={err}\n"
            )
E           RuntimeError: start_process: process exited immediately
E           cmd=['wsl', '--cd', '/mnt/c/Users/최예진/Desktop/My_Agentic_QA/target_apps/Tinyhttpd', '--', './http_server']
E           stdout=
E           stderr=/bin/bash: line 1: ./http_server: No such file or directory

tests\_harness.py:332: RuntimeError
=========================== short test summary info ===========================
FAILED tests/test_quality_check.py::test_http_server_smoke - RuntimeError: st...
1 failed in 2.56s
```

## 4. 상세 실패 원인 및 기술 분석
- **Maintainability.FunctionLOC**: Function 'accept_request' has 72 NLOC exceeding the limit.
- **Maintainability.MainLoopComplexity**: Function 'accept_request' has a cyclomatic complexity of 24 exceeding the limit.
- **FunctionalSuitability.HttpBasic**: Will be evaluated by pytest execution output
- **TestExecution.PytestRun**: {'exit_code': 1}
- **FunctionalSuitability.HttpBasic**: {'passed': 0, 'failed': 1, 'skipped': 0}

## 5. 종합 판정 및 개선 권고
- **최종 품질 등급:** 미흡
- **종합 판정:** Fail
- **우선 개선 권고 사항:**
  - Maintainability.FunctionLOC: Function 'accept_request' has 72 NLOC exceeding the limit.
  - Maintainability.MainLoopComplexity: Function 'accept_request' has a cyclomatic complexity of 24 exceeding the limit.