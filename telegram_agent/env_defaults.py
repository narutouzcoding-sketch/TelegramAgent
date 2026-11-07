"""Append newly introduced settings without rewriting existing local credentials."""

from pathlib import Path

from dotenv import dotenv_values


def ensure_env_defaults(path: Path, template: Path):
    if not template.exists():
        return []
    defaults = dotenv_values(template)
    existing = dotenv_values(path) if path.exists() else {}
    missing = [key for key in defaults if key not in existing]
    if not missing:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_bytes() if path.exists() else b""
    newline = "\r\n" if b"\r\n" in current else "\n"
    prefix = "" if not current or current.endswith((b"\n", b"\r")) else newline
    addition = (
        prefix + newline + "# Settings added by TelegramAgent; existing values preserved." + newline
    )
    addition += newline.join(f"{key}={defaults[key] or ''}" for key in missing) + newline
    with path.open("ab") as output:
        output.write(addition.encode("utf-8"))
    return missing
