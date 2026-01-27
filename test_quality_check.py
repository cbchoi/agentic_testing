import pytest
import re
import os
import sys
import ast
from pathlib import Path

@pytest.fixture(scope="session")
def core_files():
    project_root = Path(__file__).resolve().parent
    # 점수화 로직: 'pygame'을 임포트하고 게임 루프가 포함된 소스 파일(Top 1~3) 선별
    files = [str(p) for p in project_root.rglob("*.py") if "test_" not in p.name and "venv" not in str(p)]
    return files

def test_function_line_count(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            node = ast.parse(f.read())
            for n in node.body:
                if isinstance(n, ast.FunctionDef):
                    loc = n.end_lineno - n.lineno + 1
                    assert loc <= 50, f"Function '{n.name}' exceeds 50 lines (actual: {loc})"

def test_fps_variable(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            content = f.read()
            match = re.search(r'fps\s*=\s*(\d+)', content)
            if match:
                fps_value = int(match.group(1))
                assert fps_value >= 30, f"FPS value is below 30 (actual: {fps_value})"
            else:
                assert False, "No FPS value found in file"

def test_resource_loading_with_try_except(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            content = f.read()
            assert re.search(r'try:.*?(pygame\.image\.load|pygame\.mixer\.Sound|open\(\s*\w+)', content, re.DOTALL),
                f"No resource loading calls found within try/except in {file}"

def test_exit_signals(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            content = f.read()
            assert re.search(r'pygame\.QUIT|sys\.exit\(\)|running\s*=\s*False|quit\(\)', content),
                f"No exit signals found in {file}"