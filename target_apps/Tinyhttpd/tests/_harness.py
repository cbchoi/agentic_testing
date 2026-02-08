from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import time
import sys
from typing import Optional, Tuple, List, Union

_LAST_SERVER_HANDLE = None
_LAST_SERVER_EXE = None


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool

    def __iter__(self):
        # Allows: exit_code, stdout, stderr = run_command(...)
        yield self.exit_code
        yield self.stdout
        yield self.stderr

    def to_tuple3(self) -> tuple[int, str, str]:
        return (self.exit_code, self.stdout, self.stderr)



def resolve_target_dir(env_key: str = "TARGET_DIR") -> Path:
    v = os.getenv(env_key)
    if v:
        return Path(v).resolve()
    # 기본값: tests/.. (프로젝트 루트)
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

    cmd_list = [str(x) for x in list(cmd)]

    if cmd_list:
        head = cmd_list[0].lower()
        if head in ("python", "python3", "py"):
            cmd_list[0] = sys.executable

    if _should_use_wsl(cmd_list, cwd):
        cmd_list, _ = _wrap_wsl(cmd_list, cwd)
        cwd = None  # wsl --cd가 처리

    start = time.time()
    proc: Optional[subprocess.Popen] = None

    try:
        proc = subprocess.Popen(
            cmd_list,
            cwd=str(cwd) if cwd else None,
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
    blob = (stdout or "") + "\n" + (stderr or "")
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
# --- AUTO-ADDED: C/HTTP helpers (harness upgrade) ---
from dataclasses import dataclass
import socket

@dataclass
class ProcessHandle:
    popen: object
    cmd: list[str]
    cwd: str


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
        raise RuntimeError(
            "start_process: process exited immediately\n"
            f"cmd={cmd_list}\n"
            f"stdout={out}\n"
            f"stderr={err}\n"
        )

    # 2) give some time to bind
    time.sleep(0.5)

    handle = ProcessHandle(popen=p, cmd=cmd_list, cwd=orig_cwd)

    if ("darkhttpd" in exe_name) or (exe_name in ("httpd", "httpd.exe", "tinyhttpd", "tinyhttpd.exe")):
        _LAST_SERVER_HANDLE = handle
        _LAST_SERVER_EXE = exe_name

    return handle


def stop_process(proc: ProcessHandle | None) -> None:
    """
    Stop a process safely.
    - None-safe (tests may call stop_process on an uninitialized variable)
    - tolerant of already-dead processes
    """
    if not proc:
        return

    p = getattr(proc, "popen", None)
    if p is None:
        return

    try:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    finally:
        try:
            if p.stdout:
                try:
                    p.stdout.close()
                except Exception:
                    pass
            if p.stderr:
                try:
                    p.stderr.close()
                except Exception:
                    pass
        except Exception:
            pass

        
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

    raise RuntimeError(
        f"wait_for_tcp timeout after {timeout_sec}s: {host}:{port} not listening (last_err={last_err}){diag}"
    )


def http_get_raw(host: str, port: int, path: str, timeout_sec: float = 2.0) -> str:
    import socket

    try:
        if not path.startswith("/"):
            path = "/" + path

        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8", errors="ignore")

        with socket.create_connection((host, int(port)), timeout=timeout_sec) as s:
            s.settimeout(timeout_sec)
            s.sendall(req)

            chunks: list[bytes] = []
            while True:
                try:
                    buf = s.recv(65536)
                except socket.timeout:
                    break
                if not buf:
                    break
                chunks.append(buf)

        data = b"".join(chunks)
        return data.decode("utf-8", errors="ignore")

    except Exception as e:
        return f"[HTTP_GET_RAW_ERROR] {type(e).__name__}: {e}"


def _to_wsl_path(win_path: str) -> str:
    p = str(Path(win_path).resolve())
    m = re.match(r"^([A-Za-z]):\\(.*)$", p)
    if not m:
        return p.replace("\\", "/")
    drive = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"

def _should_use_wsl(cmd: list[str], cwd: Path | None) -> bool:
    if not cmd:
        return False

    head = str(cmd[0])

    # 1) make는 무조건 WSL
    if head.lower() == "make":
        return True

    # 2) ./xxx 형태도 WSL
    if head.startswith("./"):
        return True
    
    if head.startswith("/mnt/"):
        return True

    # 3) "C:\...\something" 처럼 Windows 경로로 들어온 실행 파일도 WSL로
    #    (특히 확장자 없는 바이너리: darkhttpd, tinyhttpd 등)
    if re.match(r"^[A-Za-z]:\\", head) or re.match(r"^[A-Za-z]:/", head):
        stem = Path(head).name.lower()
        # 확장자 없는 파일이거나, .out 같은 리눅스 계열 산출물일 가능성이 크면 WSL
        if "." not in stem:
            return True
        # 혹시라도 darkhttpd/tinyhttpd 같은 키워드면 WSL
        if "httpd" in stem or "tiny" in stem or "dark" in stem:
            return True

    return False

def _wrap_wsl(cmd: list[str], cwd: Path | None) -> tuple[list[str], None]:
    # wsl --cd <cwd_wsl> -- <cmd...>
    if cwd is None:
        return (["wsl", "--"] + cmd, None)
    cwd_wsl = _to_wsl_path(str(cwd))
    return (["wsl", "--cd", cwd_wsl, "--"] + cmd, None)

def run_command3(cmd: list[str], cwd: Path | None = None, timeout_sec: int = 10) -> tuple[int, str, str]:
    r = run_command(cmd, cwd=cwd, timeout_sec=timeout_sec)
    return (r.exit_code, r.stdout, r.stderr)


def find_pygame_entrypoint(
    base_dir: Path | None = None,
    prefer: list[str] | None = None,
) -> Path:
    """
    Find a likely pygame entry script in the target directory.

    Strategy:
    1) Prefer common filenames if present (main.py, game.py, run.py, app.py, etc.)
    2) Scan *.py for pygame signals and a runnable main block
    3) Fallback: first non-test .py file
    """
    base_dir = (base_dir or resolve_target_dir()).resolve()

    if prefer is None:
        prefer = [
            "main.py",
            "game.py",
            "run.py",
            "app.py",
            "breakout.py",
            "space_invaders.py",
            "flappybird.py",
        ]

    for name in prefer:
        p = base_dir / name
        if p.exists() and p.is_file():
            return p

    candidates: list[Path] = []
    for p in base_dir.rglob("*.py"):
        s = str(p)
        if "\\tests\\" in s or "/tests/" in s:
            continue
        if p.name.startswith("test_"):
            continue
        if p.name == "_harness.py":
            continue
        if "__pycache__" in s:
            continue
        candidates.append(p)

    def _score(path: Path) -> int:
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0

        score = 0
        low = src.lower()

        if "import pygame" in low:
            score += 3
        if "pygame.init" in low:
            score += 2
        if "pygame.display.set_mode" in low:
            score += 2
        if "pygame.event.get" in low:
            score += 1
        if "while" in low and "pygame" in low:
            score += 1
        if 'if __name__ == "__main__"' in src:
            score += 2

        return score

    if candidates:
        candidates_sorted = sorted(candidates, key=_score, reverse=True)
        if _score(candidates_sorted[0]) > 0:
            return candidates_sorted[0]
        return candidates_sorted[0]

    raise FileNotFoundError(f"no python entry file found under {base_dir}")
