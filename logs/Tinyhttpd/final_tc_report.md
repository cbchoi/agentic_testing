# [최종 품질 통합 보고서]

## 1. 정적 분석 요약 (에이전트 1 결과)
| Check ID | Pass | Weight | FailureType | Responsibility | Evidence |
|---|---:|---:|---|---|---|
| UNKNOWN::Unknown | None | 0 | TEST_ASSUMPTION_VIOLATION | QA_AGENT |  |
| TestExecution.PytestRun | False | 0.0 | TEST_ASSUMPTION_VIOLATION | QA_AGENT | {'exit_code': 1} |
| FunctionalSuitability.HttpBasic | False | 0.4 | TEST_ASSUMPTION_VIOLATION | QA_AGENT | {'passed': 0, 'failed': 1, 'skipped': 0} |

## 2. 동적 테스트 결과 요약
- **직접 실행 상태:** 실패
- **테스트 성공 개수:** 0 / **실패 개수:** 1

## 3. pytest 실행 증명 로그 (원문)
```text
F                                                                        [100%]
================================== FAILURES ===================================
___________________________ test_http_server_smoke ____________________________

    def test_http_server_smoke():
        target_dir = resolve_target_dir()
        try:
            run_command(["make"], cwd=target_dir)
            server_handle = start_process(["./httpd"], cwd=target_dir)
>           wait_for_tcp(8080)

tests\test_quality_check.py:8: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

timeout_sec = 15, args = (8080,), host = '127.0.0.1', start = 1770230296.6752868

    def wait_for_tcp(*args, timeout_sec: int = 15) -> bool:
        """
        - wait_for_tcp(8080)
        - wait_for_tcp("127.0.0.1", 8080)
    
        Behavior:
        - If server process dies => fail fast with stdout/stderr
        - Only checks the requested port (no fallback ports)
        - On timeout, attach WSL/Linux listening diagnostics (ss/netstat) + pid
        """
        global _LAST_SERVER_HANDLE, _LAST_SERVER_EXE
    
        if len(args) == 1:
            host, port = "127.0.0.1", int(args[0])
        elif len(args) == 2:
            host, port = str(args[0]), int(args[1])
        else:
            raise TypeError("wait_for_tcp expects (port) or (host, port)")
    
        start = time.time()
        last_err = None
    
        def _best_effort_listen_diag() -> str:
            """
            If running under WSL, show whether anything is listening on :port.
            Works even when stdout/stderr from the server is empty.
            """
            pid = None
            if _LAST_SERVER_HANDLE is not None:
                popen = getattr(_LAST_SERVER_HANDLE, "popen", None)
                if popen is not None:
                    pid = getattr(popen, "pid", None)
    
            # Prefer ss, fallback to netstat
            # Note: We intentionally run via WSL to inspect Linux-side sockets.
            lines = []
            try:
                # ss output (Linux)
                r1 = run_command(["wsl", "--", "bash", "-lc", f"ss -ltnp 2>/dev/null | grep ':{port} ' || true"], cwd=None, timeout_sec=3)
                if r1.stdout.strip():
                    lines.append("[wsl:ss]")
                    lines.append(r1.stdout.strip())
            except Exception:
                pass
    
            try:
                r2 = run_command(["wsl", "--", "bash", "-lc", f"netstat -ltnp 2>/dev/null | grep ':{port} ' || true"], cwd=None, timeout_sec=3)
                if r2.stdout.strip():
                    lines.append("[wsl:netstat]")
                    lines.append(r2.stdout.strip())
            except Exception:
                pass
    
            if pid is not None:
                lines.append(f"[server pid] {pid}")
            if _LAST_SERVER_EXE:
                lines.append(f"[server exe] {_LAST_SERVER_EXE}")
    
            return "\n".join(lines).strip()
    
        while time.time() - start < timeout_sec:
            # 1) server died => fail fast
            if _LAST_SERVER_HANDLE is not None:
                popen = getattr(_LAST_SERVER_HANDLE, "popen", None)
                if popen is not None and popen.poll() is not None:
                    try:
                        out, err = popen.communicate(timeout=1)
                    except Exception:
                        out, err = "", ""
                    raise RuntimeError(
                        "server process exited before listening\n"
                        f"exe={_LAST_SERVER_EXE}\n"
                        f"stdout={out}\n"
                        f"stderr={err}\n"
                    )
    
            # 2) check only requested port
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError as e:
                last_err = e
    
            time.sleep(0.2)
    
        diag = _best_effort_listen_diag()
        diag = ("\n" + diag) if diag else ""
    
>       raise RuntimeError(
            f"wait_for_tcp timeout after {timeout_sec}s: {host}:{port} not listening (last_err={last_err}){diag}"
        )
E       RuntimeError: wait_for_tcp timeout after 15s: 127.0.0.1:8080 not listening (last_err=timed out)
E       [server pid] 27968
E       [server exe] httpd

tests\_harness.py:461: RuntimeError
=========================== short test summary info ===========================
FAILED tests/test_quality_check.py::test_http_server_smoke - RuntimeError: wa...
1 failed in 19.98s
```

## 4. 상세 실패 원인 및 기술 분석
- **TestExecution.PytestRun**: {'exit_code': 1}
- **FunctionalSuitability.HttpBasic**: {'passed': 0, 'failed': 1, 'skipped': 0}

## 5. 종합 판정 및 개선 권고
- **최종 품질 등급:** 미흡
- **종합 판정:** Fail
- **우선 개선 권고 사항:**
  - TestExecution.PytestRun: {'exit_code': 1}
  - FunctionalSuitability.HttpBasic: {'passed': 0, 'failed': 1, 'skipped': 0}