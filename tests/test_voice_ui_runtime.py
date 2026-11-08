import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_microphone_file_races_and_hidden_capture_are_prevented():
    node = shutil.which("node")
    if not node:
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe"
        node = str(candidate) if candidate.is_file() else None
    if not node:
        pytest.skip("Node is needed for browser-component unit tests")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("js") / "voice-ui.test.cjs")],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
