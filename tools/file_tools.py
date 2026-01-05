import subprocess
from crewai.tools import BaseTool
from pydantic import Field

class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "파일의 내용을 읽어오는 도구입니다. 인자로 file_path를 받습니다."

    def _run(self, file_path: str) -> str:
        with open(file_path.strip(), 'r', encoding='utf-8') as f:
            return f.read()

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
            result = subprocess.run(['python', file_path.strip()], capture_output=True, text=True, timeout=15)
            return f"출력: {result.stdout}\n에러: {result.stderr}"
        except Exception as e:
            return f"실행 오류: {str(e)}"