import os
import subprocess
import shutil
import stat
from crewai.tools import BaseTool
from pydantic import Field

# Windows의 읽기 전용 파일 삭제 권한 문제를 해결하기 위한 콜백 함수
def on_rm_error(func, path, exc_info):
    """
    파일 삭제 중 권한 오류 발생 시 읽기 전용 속성을 해제하고 다시 시도합니다.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)

class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "파일의 내용을 읽어오는 도구입니다. 인자로 file_path를 받습니다."

    def _run(self, file_path: str) -> str:
        try:
            with open(file_path.strip(), 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"파일 읽기 오류: {str(e)}"

class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = "파일에 내용을 씁니다. '파일명|내용' 형식의 단일 문자열을 인자로 받습니다."

    def _run(self, data: str) -> str:
        try:
            if '|' not in data:
                return "오류: '파일명|내용' 형식을 지켜주세요."
            file_path, content = data.split('|', 1)
            with open(file_path.strip(), 'w', encoding='utf-8') as f:
                f.write(content)
            return f"성공적으로 {file_path}를 수정했습니다."
        except Exception as e:
            return f"파일 쓰기 오류: {str(e)}"

class ExecuteScriptTool(BaseTool):
    name: str = "execute_script"
    description: str = "파이썬 스크립트를 실행합니다. 인자로 file_path를 받습니다."

    def _run(self, file_path: str) -> str:
        try:
            # 타임아웃을 15초로 설정하여 무한 루프 방지
            result = subprocess.run(['python', file_path.strip()], capture_output=True, text=True, timeout=15)
            return f"출력: {result.stdout}\n에러: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "오류: 스크립트 실행 시간이 초과되었습니다 (15초)."
        except Exception as e:
            return f"실행 오류: {str(e)}"

class ListFilesTool(BaseTool):
    name: str = "list_files"
    description: str = "특정 폴더 내의 파일 목록을 보여줍니다. 경로를 인자로 받습니다 (예: 'target_apps/cloned_app')."

    def _run(self, directory_path: str) -> str:
        try:
            path = directory_path.strip()
            if os.path.exists(path):
                files = os.listdir(path)
                return f"'{path}' 폴더 내 파일 목록: {files}"
            else:
                return f"오류: '{path}' 경로가 존재하지 않습니다."
        except Exception as e:
            return f"목록 확인 실패: {str(e)}"

class GitCloneTool(BaseTool):
    name: str = "git_clone"
    description: str = "깃허브 저장소 URL을 인자로 받아 소스코드를 내려받습니다. 예: 'https://github.com/user/repo'"

    def _run(self, repo_url: str) -> str:
        try:
            target_dir = os.path.abspath('target_apps/cloned_app')
            clean_url = repo_url.strip()
            
            # 1. 기존 폴더가 있다면 강제 삭제 (Windows 권한 이슈 대응)
            if os.path.exists(target_dir):
                print(f"DEBUG: 기존 폴더 제거 중... {target_dir}")
                shutil.rmtree(target_dir, onerror=on_rm_error)
            
            # 2. 부모 디렉토리 생성
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            
            # 3. Git 클론 실행
            print(f"DEBUG: 실행 중인 명령 -> git clone {clean_url} {target_dir}")
            result = subprocess.run(
                ['git', 'clone', clean_url, target_dir],
                capture_output=True, text=True, check=True
            )
            
            return f"성공: {clean_url}을 {target_dir}에 복사했습니다. 분석을 시작하세요."
        except Exception as e:
            return f"오류 발생: {str(e)}. 주소가 정확한지, Git이 설치되어 있는지 확인하세요."