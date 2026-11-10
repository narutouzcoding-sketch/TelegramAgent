import subprocess
import sys

import pytest

from telegram_agent.instance_lock import instance_lock


def test_other_process_cannot_start_until_lock_is_released(tmp_path):
    path = tmp_path / "agent.lock"
    code = """
import sys
from pathlib import Path
from telegram_agent.instance_lock import instance_lock
try:
    with instance_lock(Path(sys.argv[1])):
        print('acquired')
except ValueError:
    print('busy')
"""
    with instance_lock(path):
        child = subprocess.run(
            [sys.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=10
        )
        assert child.returncode == 0 and child.stdout.strip() == "busy"
    child = subprocess.run(
        [sys.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=10
    )
    assert child.returncode == 0 and child.stdout.strip() == "acquired"


def test_lock_is_released_after_worker_failure(tmp_path):
    path = tmp_path / "agent.lock"
    with pytest.raises(RuntimeError):
        with instance_lock(path):
            raise RuntimeError("worker failed")
    with instance_lock(path):
        pass
