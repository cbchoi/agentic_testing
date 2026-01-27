import sys
import os
import pytest
import re
import ast
from pathlib import Path

@pytest.fixture(scope="session")
def core_files():
    project_root = Path(__file__).resolve().parent
    files = [str(p) for p in project_root.rglob("*.py") if "test_" not in p.name and "venv" not in str(p)]
    return files

def test_function_line_count(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            node = ast.parse(f.read())
            for n in [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]:
                function_line_count = n.end_lineno - n.lineno + 1
                assert function_line_count <= 50, f'Fail: Function "{n.name}" has {function_line_count} lines, exceeding the limit of 50.'


def test_fps_value(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            contents = f.read()
            match = re.search(r'\bclock\.tick\((\d+)\)', contents)
            if match:
                fps_value = int(match.group(1))
                assert fps_value >= 30, f'Fail: Frame rate (fps) is {fps_value}, expected at least 30.'


def test_exception_handling(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            contents = f.read()
            assert re.search(r'try:|except:', contents) is not None, f'Fail: No try/except block found in {file}.'


def test_exit_signals(core_files):
    for file in core_files:
        with open(file, 'r') as f:
            contents = f.read()
            assert re.search(r'pygame\.QUIT|sys\.exit|running\s*=\s*False|quit\(\)', contents) is not None, f'Fail: No exit signal found in {file}.'