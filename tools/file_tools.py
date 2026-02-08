import os
import subprocess
import shutil
import stat
import sys
import json
import re
from pathlib import Path
from crewai.tools import BaseTool


def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "파일의 내용을 읽어오는 도구입니다. 인자로 file_path를 받습니다."

    def __init__(self, allowed_root: str = None, **kwargs):
        super().__init__(**kwargs)
        self._allowed_root = Path(allowed_root).resolve() if allowed_root else None

    def _run(self, file_path: str) -> str:
        p = (file_path or "").strip()
        try:
            fp = Path(p).resolve()

            if self._allowed_root:
                try:
                    fp.relative_to(self._allowed_root)
                except ValueError:
                    return (
                        "[READ_FILE_DENIED]\n"
                        f"allowed_root={self._allowed_root}\n"
                        f"requested={fp}"
                    )

            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            return f"[READ_FILE_ERROR] path={p} error={type(e).__name__}: {e}"


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = "파일에 내용을 씁니다. '파일명|내용' 형식의 단일 문자열을 인자로 받습니다."

    def _run(self, data: str) -> str:
        try:
            if "|" not in data:
                return "[WRITE_FILE_ERROR] format must be 'file_path|content'"

            file_path, content = data.split("|", 1)
            p = file_path.strip()
            parent = os.path.dirname(p)
            if parent:
                os.makedirs(parent, exist_ok=True)

            raw = content
            if raw is None:
                raw = ""
            raw = str(raw).lstrip("\ufeff").strip()

            # 1) code fence 제거
            raw = raw.replace("```python", "").replace("```", "").strip()

            # 2) JSON으로 감싸진 경우 풀기: "....", {"code":"..."}, {"content":"..."} 등
            try:
                import json
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

            # 3) escape 문자열이 “문서 전체에 많이 있고”, 실제 줄바꿈이 거의 없으면 복원
            real_newlines = raw.count("\n")
            escaped_newlines = raw.count("\\n") + raw.count("\\r\\n")
            if escaped_newlines >= 2 and real_newlines <= 1:
                raw = raw.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")

            # 4) import/from 시작점 강제 (앞에 잡문 붙는 케이스 제거)
            import re
            m = re.search(r"^(?:from\s+\S+\s+import\s+|import\s+\S+)", raw, flags=re.MULTILINE)
            if m:
                raw = raw[m.start():].lstrip()

            # 5) 최종 저장
            with open(p, "w", encoding="utf-8", errors="ignore") as f:
                f.write(raw.rstrip() + "\n")

            return f"[WRITE_FILE_OK] path={p} bytes={len(raw.encode('utf-8', errors='ignore'))}"
        except Exception as e:
            return f"[WRITE_FILE_ERROR] error={type(e).__name__}: {e}"


from pathlib import Path
import os
from crewai.tools import BaseTool  # 이미 쓰고 있는 BaseTool import 경로에 맞춰 유지

class ListFilesTool(BaseTool):
    name: str = "list_files"
    description: str = (
        "특정 폴더 하위의 파일 목록을 재귀로 보여줍니다.\n"
        "인자: directory_path (예: 'target_apps/cloned_app')"
    )

    def __init__(self, allowed_root: str = None, **kwargs):
        super().__init__(**kwargs)
        self._allowed_root = Path(allowed_root).resolve() if allowed_root else None

    def _run(self, directory_path: str) -> str:
        base = (directory_path or "").strip()
        try:
            base_path = Path(base).resolve()

            if not base_path.exists():
                return f"[LIST_FILES_ERROR] path_not_found={base_path}"

            if not base_path.is_dir():
                return f"[LIST_FILES_ERROR] not_a_directory={base_path}"

            if self._allowed_root:
                try:
                    # base_path가 allowed_root 하위인지 판정
                    base_path.relative_to(self._allowed_root)
                except ValueError:
                    return (
                        "[LIST_FILES_DENIED]\n"
                        f"allowed_root={self._allowed_root}\n"
                        f"requested={base_path}"
                    )

            exclude_dir_names = {"venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
            exclude_path_parts = {os.sep + n + os.sep for n in exclude_dir_names}

            files = []
            total = 0
            for p in base_path.rglob("*"):
                total += 1
                sp = str(p)
                if any(part in sp for part in exclude_path_parts):
                    continue
                if p.is_file():
                    files.append(sp)

            files.sort()
            head = files[:200]

            return (
                f"[LIST_FILES_OK]\n"
                f"base_dir={base_path}\n"
                f"scanned_nodes={total}\n"
                f"file_count={len(files)}\n"
                f"files_head(<=200)=\n" + "\n".join(head)
            )
        except Exception as e:
            return f"[LIST_FILES_ERROR] base={base} error={type(e).__name__}: {e}"


class GitCloneTool(BaseTool):
    name: str = "git_clone"
    description: str = "깃허브 저장소 URL을 인자로 받아 소스코드를 내려받습니다. 예: 'https://github.com/user/repo'"

    def _run(self, repo_url: str) -> str:
        try:
            target_dir = os.path.abspath("target_apps/cloned_app")
            clean_url = repo_url.strip()

            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, onerror=on_rm_error)

            os.makedirs(os.path.dirname(target_dir), exist_ok=True)

            result = subprocess.run(
                ["git", "clone", clean_url, target_dir],
                capture_output=True,
                text=True,
                check=True,
            )
            return f"[GIT_CLONE_OK] url={clean_url} target_dir={target_dir}\n{result.stdout}"
        except Exception as e:
            return f"[GIT_CLONE_ERROR] error={type(e).__name__}: {e}"


class RunPytestTool(BaseTool):
    name: str = "run_pytest"
    description: str = (
        "pytest를 실행하고 결과(exit_code/stdout/stderr)와 환경정보를 반환합니다.\n"
        "입력 형식: 'base_dir|args'\n"
        "예) 'target_apps/space_invaders|test_quality_check.py -q'\n"
        "예) 'target_apps/breakout|-q'\n"
    )

    def _preflight(self, base_dir: str) -> str | None:
        """
        pytest 실행 전 테스트 산출물이 깨져서 (NameError/SyntaxError/하네스 누락 등)
        타겟 결함과 섞이는 문제를 방지하기 위한 게이트.
        실패 시 pytest를 실행하지 않고 즉시 에러 문자열을 반환한다.
        """
        try:
            tests_dir = Path(base_dir) / "tests"
            if not tests_dir.exists() or not tests_dir.is_dir():
                return None

            test_files = sorted(tests_dir.glob("test_*.py"))
            if not test_files:
                return None

            for tf in test_files:
                src = tf.read_text(encoding="utf-8", errors="ignore")

                # 자동 정규화/복구
                src = self._normalize_test_source(src)
                src2, changed = self._ensure_harness_import_at_top(src)

                if changed and src2 != src:
                    try:
                        tf.write_text(src2, encoding="utf-8")
                        src = src2
                    except Exception:
                        # 쓰기 실패해도 검사/실행은 계속 시도
                        src = src2

                # 1) 하네스 임포트 강제
                if not re.search(
                    r"^\s*from\s+tests\._harness\s+import\b",
                    src,
                    flags=re.MULTILINE,
                ):
                    return (
                        "[PREFLIGHT_FAIL] harness_not_imported\n"
                        f"file={tf.name}\n"
                        "hint=Tests must import from 'tests._harness' near the top.\n"
                        "classify=TEST_ARTIFACT_INVALID"
                    )

                # 2) 파일 헤더 강제: 주석/encoding/docstring 이후 첫 문장이 하네스 import여야 함
                lines = src.splitlines()
                i = 0

                while i < len(lines):
                    s = lines[i].strip()
                    if not s:
                        i += 1
                        continue
                    if s.startswith("#!"):
                        i += 1
                        continue
                    if s.startswith("#"):
                        i += 1
                        continue
                    if "coding" in s and s.startswith("#"):
                        i += 1
                        continue
                    break

                if i < len(lines) and lines[i].lstrip().startswith(('"""', "'''")):
                    quote = '"""' if lines[i].lstrip().startswith('"""') else "'''"
                    if lines[i].count(quote) >= 2:
                        i += 1
                    else:
                        i += 1
                        while i < len(lines) and quote not in lines[i]:
                            i += 1
                        i += 1

                while i < len(lines) and not lines[i].strip():
                    i += 1

                if i >= len(lines) or not lines[i].lstrip().startswith("from tests._harness import"):
                    return (
                        "[PREFLIGHT_FAIL] bad_file_header\n"
                        f"file={tf.name}\n"
                        "hint=File must import 'from tests._harness import (...)' near the top (comments/docstring allowed).\n"
                        "classify=TEST_ARTIFACT_INVALID"
                    )

                # 3) stray 텍스트 블록 방지
                inside_import_block = False
                symbols = [
                    "resolve_target_dir",
                    "resolve_file",
                    "read_text_file",
                    "run_command",
                    "summarize_exception",
                    "start_process",
                    "stop_process",
                    "wait_for_tcp",
                    "http_get_raw",
                ]
                sym_pattern = re.compile(
                    r"^\s*\(?\s*(" + "|".join(map(re.escape, symbols)) + r")\s*,\s*$"
                )

                for ln in lines:
                    s = ln.strip()

                    if s.startswith("from tests._harness import"):
                        if "(" in s and ")" not in s:
                            inside_import_block = True
                        else:
                            inside_import_block = False
                        continue

                    if inside_import_block:
                        if s.startswith(")") or s == ")" or s.endswith(")"):
                            inside_import_block = False
                        continue

                    if sym_pattern.match(ln):
                        return (
                            "[PREFLIGHT_FAIL] stray_text_block\n"
                            f"file={tf.name}\n"
                            "hint=Found comma-separated harness symbol outside the import block.\n"
                            "classify=TEST_ARTIFACT_INVALID"
                        )

                # 4) 문법 체크
                try:
                    compile(src, str(tf), "exec")
                except Exception as e:
                    return (
                        "[PREFLIGHT_FAIL] syntax_error\n"
                        f"file={tf.name}\n"
                        f"error={type(e).__name__}: {e}\n"
                        "classify=TEST_ARTIFACT_INVALID"
                    )

            return None

        except Exception as e:
            return (
                "[PREFLIGHT_ERROR]\n"
                f"error={type(e).__name__}: {e}\n"
                "classify=TEST_ARTIFACT_INVALID"
            )

    def _run(self, data: str = "") -> str:
        try:
            if "|" not in (data or ""):
                return json.dumps({
                    "exit_code": 2,
                    "stdout": "",
                    "stderr": "[RUN_PYTEST_ERROR] format must be 'base_dir|args'",
                })

            base_dir_raw, args_raw = data.split("|", 1)
            base_dir = os.path.abspath(base_dir_raw.strip())
            args = (args_raw or "").strip()

            if not os.path.isdir(base_dir):
                return json.dumps({
                    "exit_code": 2,
                    "stdout": "",
                    "stderr": f"[RUN_PYTEST_ERROR] base_dir_not_found={base_dir}",
                })

            py = sys.executable
            env = os.environ.copy()

            repo_root = Path(__file__).resolve().parents[1]

            existing = env.get("PYTHONPATH", "")
            path_entries = [str(repo_root), base_dir]
            if existing:
                path_entries.append(existing)
            env["PYTHONPATH"] = os.pathsep.join(path_entries)

            # pygame headless 안정화
            env.setdefault("SDL_VIDEODRIVER", "dummy")
            env.setdefault("SDL_AUDIODRIVER", "dummy")
            env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

            env["TARGET_DIR"] = base_dir

            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            env["PYTHONNOUSERSITE"] = "1"

            # --- Preflight Gate ---
            preflight_error = self._preflight(base_dir)
            if preflight_error:
                return json.dumps({
                    "exit_code": 2,
                    "stdout": "",
                    "stderr": preflight_error,
                })
            # ----------------------

            # pytest version
            try:
                version = subprocess.run(
                    [py, "-m", "pytest", "--version"],
                    cwd=base_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,
                    env=env,
                )
                pytest_version = (version.stdout.strip() or version.stderr.strip())
            except Exception as e:
                pytest_version = f"(failed to get version: {type(e).__name__}: {e})"

            # import 충돌 방지
            cmd = [py, "-m", "pytest", "--import-mode=importlib"]

            if args:
                cmd += args.split()
            else:
                default_test = str(Path("tests") / "test_quality_check.py")
                cmd += [default_test, "-q"]

            result = subprocess.run(
                cmd,
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=120,
                shell=False,
                env=env,
            )

            return json.dumps({
                "exit_code": int(result.returncode),
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "meta": {
                    "python": py,
                    "cwd": base_dir,
                    "target_dir": env.get("TARGET_DIR"),
                    "pythonpath": env.get("PYTHONPATH", ""),
                    "pytest_version": pytest_version,
                    "cmd": " ".join(cmd),
                    "pytest_disable_plugin_autoload": env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD", ""),
                    "pythonnousersite": env.get("PYTHONNOUSERSITE", ""),
                },
            })

        except subprocess.TimeoutExpired:
            return json.dumps({
                "exit_code": 2,
                "stdout": "",
                "stderr": "[RUN_PYTEST_ERROR] timeout=120s",
            })
        except Exception as e:
            return json.dumps({
                "exit_code": 2,
                "stdout": "",
                "stderr": f"[RUN_PYTEST_ERROR] {type(e).__name__}: {e}",
            })

        
    def _normalize_test_source(self, src: str) -> str:
        # 0) BOM 제거
        src = src.lstrip("\ufeff")

        # 1) "assert <expr>," (콤마로 끝나는 assert) 자동 복구
        #    - assert expr, "msg" 는 건드리지 않음 (콤마 뒤가 있으니까)
        src = re.sub(
            r"(?m)^(\s*assert\s+.+?),\s*$",
            r"\1",
            src,
        )

        return src

    def _ensure_harness_import_at_top(self, src: str) -> tuple[str, bool]:
        """
        returns: (new_src, changed)
        - tests._harness import가 어딘가에 있으면 해당 import 블록(멀티라인 포함)을 최상단으로 끌어올린다.
        - 없으면 최상단에 'from tests._harness import *'를 삽입한다.
        """
        import re

        changed = False
        lines = src.splitlines()

        # 1) 기존 harness import "블록" 찾기
        start = None
        end = None
        for i, line in enumerate(lines):
            if re.search(r"\bfrom\s+tests\._harness\s+import\b", line):
                start = i
                # 멀티라인 import 블록 처리
                if "(" in line and ")" not in line:
                    j = i + 1
                    while j < len(lines):
                        if ")" in lines[j]:
                            end = j
                            break
                        j += 1
                    if end is None:
                        end = i
                else:
                    end = i
                break

        if start is None:
            harness_block = ["from tests._harness import *"]
            changed = True
        else:
            harness_block = lines[start : end + 1]
            # 기존 위치에서 블록 제거
            del lines[start : end + 1]
            changed = True

        # 2) 최상단 prefix 보존 (shebang/encoding)
        prefix = []
        if lines and lines[0].startswith("#!"):
            prefix.append(lines.pop(0))
        if lines and re.match(r"^#.*coding[:=]\s*[-\w.]+", lines[0]):
            prefix.append(lines.pop(0))

        # 3) 최상단에 harness 블록 삽입 (빈 줄 하나 넣어서 가독성)
        new_lines = prefix + harness_block + [""] + lines
        new_src = "\n".join(new_lines).rstrip() + "\n"
        return new_src, changed

class RunWSLCommandTool(BaseTool):
    name: str = "run_wsl_command"
    description: str = (
        "WSL(Ubuntu)에서 명령을 실행합니다.\n"
        "입력 형식: 'base_dir|command'\n"
        "예) 'target_apps/darkhttpd|make'\n"
    )

    def _to_wsl_path(self, win_path: str) -> str:
        p = str(Path(win_path).resolve())
        m = re.match(r"^([A-Za-z]):\\(.*)$", p)
        if not m:
            return p.replace("\\", "/")
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"

    def _run(self, data: str = "") -> str:
        try:
            if "|" not in (data or ""):
                return "[RUN_WSL_COMMAND_ERROR] format must be 'base_dir|command'"

            base_dir_raw, cmd_raw = data.split("|", 1)
            base_dir = os.path.abspath(base_dir_raw.strip())
            cmd = (cmd_raw or "").strip()

            if not os.path.isdir(base_dir):
                return f"[RUN_WSL_COMMAND_ERROR] base_dir_not_found={base_dir}"

            # 핵심: wslpath 호출 제거하고, /mnt/... 로 직접 변환
            wsl_dir = self._to_wsl_path(base_dir)

            # wsl --cd 로 디렉토리 이동을 맡기고, bash -lc로 명령 실행
            result = subprocess.run(
                ["wsl", "--cd", wsl_dir, "--", "bash", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=180,
                shell=False,
            )

            return (
                f"CWD_WIN: {base_dir}\n"
                f"CWD_WSL: {wsl_dir}\n"
                f"CMD: {cmd}\n"
                f"EXIT_CODE: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )

        except subprocess.TimeoutExpired:
            return "[RUN_WSL_COMMAND_TIMEOUT] timeout=180s"
        except Exception as e:
            return f"[RUN_WSL_COMMAND_ERROR] {type(e).__name__}: {e}"
