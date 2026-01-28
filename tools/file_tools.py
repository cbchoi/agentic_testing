import os
import subprocess
import shutil
import stat
import sys
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

    def _run(self, data: str = "") -> str:
        try:
            if "|" not in (data or ""):
                return "[RUN_PYTEST_ERROR] format must be 'base_dir|args'"

            base_dir_raw, args_raw = data.split("|", 1)
            base_dir = os.path.abspath(base_dir_raw.strip())
            args = (args_raw or "").strip()

            if not os.path.isdir(base_dir):
                return f"[RUN_PYTEST_ERROR] base_dir_not_found={base_dir}"

            py = sys.executable

            version = subprocess.run(
                [py, "-m", "pytest", "--version"],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )

            cmd = [py, "-m", "pytest"]
            if args:
                cmd += args.split()

            result = subprocess.run(
                cmd,
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=120,
                shell=False,
            )

            return (
                f"PYTHON: {py}\n"
                f"CWD: {base_dir}\n"
                f"PYTEST_VERSION: {(version.stdout.strip() or version.stderr.strip())}\n"
                f"CMD: {' '.join(cmd)}\n"
                f"EXIT_CODE: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )

        except subprocess.TimeoutExpired:
            return "[RUN_PYTEST_ERROR] timeout=120s"
        except Exception as e:
            return f"[RUN_PYTEST_ERROR] error={type(e).__name__}: {e}"

class RunWSLCommandTool(BaseTool):
    name: str = "run_wsl_command"
    description: str = (
        "WSL(Ubuntu)에서 명령을 실행합니다.\n"
        "입력 형식: 'base_dir|command'\n"
        "예) 'target_apps/darkhttpd|make'\n"
        "예) 'target_apps/Tinyhttpd|cppcheck --enable=warning,style,performance,portability --quiet .'\n"
        "예) 'target_apps/Tinyhttpd|lizard -l c -C 15 .'\n"
    )

    def _run(self, data: str = "") -> str:
        try:
            if "|" not in (data or ""):
                return "[RUN_WSL_COMMAND_ERROR] format must be 'base_dir|command'"

            base_dir_raw, cmd_raw = data.split("|", 1)
            base_dir = os.path.abspath(base_dir_raw.strip())
            cmd = (cmd_raw or "").strip()

            if not os.path.isdir(base_dir):
                return f"[RUN_WSL_COMMAND_ERROR] base_dir_not_found={base_dir}"

            # Windows path -> WSL path
            wslpath = subprocess.run(
                ["wsl", "wslpath", "-a", base_dir],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            if wslpath.returncode != 0:
                return (
                    "[RUN_WSL_COMMAND_ERROR] wslpath_failed\n"
                    f"EXIT_CODE: {wslpath.returncode}\n"
                    f"STDOUT:\n{wslpath.stdout}\n"
                    f"STDERR:\n{wslpath.stderr}\n"
                )

            wsl_dir = (wslpath.stdout or "").strip()
            wsl_cmd = f'cd "{wsl_dir}" && {cmd}'

            result = subprocess.run(
                ["wsl", "bash", "-lc", wsl_cmd],
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
