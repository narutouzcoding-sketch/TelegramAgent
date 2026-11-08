"""Restart a crashed local panel, while respecting a clean owner shutdown."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import ROOT


def panel_available():
    try:
        with urlopen("http://127.0.0.1:8765/api/session", timeout=2) as response:
            return "authenticated" in json.load(response)
    except (URLError, OSError, ValueError):
        return False


def supervise(root=ROOT, process_factory=None, pause=time.sleep, available=panel_available):
    # Do not take over a manually running panel or open a duplicate Telegram session.
    if available():
        return 0
    process_factory = process_factory or subprocess.Popen
    folder = Path(root) / "data"
    folder.mkdir(exist_ok=True, parents=True)
    failures = 0
    while failures < 5:
        path = folder / "service.log"
        if path.exists() and path.stat().st_size > 2_000_000:
            path.replace(folder / "service.previous.log")
        with path.open("ab") as output:
            began = time.monotonic()
            process = process_factory(
                [sys.executable, "-m", "telegram_agent", "panel"],
                cwd=str(root),
                stdout=output,
                stderr=output,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            try:
                result = process.wait()
            except KeyboardInterrupt:
                process.terminate()
                process.wait()
                return 0
            if result == 0:
                return 0
            if time.monotonic() - began > 300:
                failures = 0
            failures += 1
            output.write(f"\nPanel exited code={result}; restart attempt={failures}/5\n".encode())
        if failures < 5:
            pause(min(60, 2**failures))
            if available():
                return 0
    # Bounded startup failures require review, not a permanent relogin loop.
    return 0
