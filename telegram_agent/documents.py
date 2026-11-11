"""Opt-in, local-only selected-folder search. No embeddings, network or file writes."""

import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from .store import utc_now

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


class PrivateReply(str):
    """Owner-visible text that must not be passed to any online speech/LLM API."""


SKIP = {"node_modules", "__pycache__", "data", "logs", "backups", "credentials", "secrets"}
STOP = set(
    "hujjat hujjatlar fayl fayllar papka papkadagi ichida ichidan mening men menga haqida nima qaysi qidir top ko'rsat korsat ayt ma'lumot malumot va bilan uchun shu document documents file folder search find pdf docx txt md".split()
)


def words(text):
    return {w for w in re.findall(r"[^\W_]{2,}", text.casefold()) if w not in STOP}


class DocumentLibrary:
    def __init__(self, store):
        self.store = store
        store.db.executescript("""
            CREATE TABLE IF NOT EXISTS library_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY,source TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,kind TEXT NOT NULL,created TEXT NOT NULL);
        """)

    def settings(self):
        return dict(self.store.db.execute("SELECT key,value FROM library_settings"))

    def status(self):
        cfg = self.settings()
        counts = dict(self.store.db.execute("SELECT kind,COUNT(*) FROM documents GROUP BY kind"))
        return {
            "folder": cfg.get("folder", ""),
            "indexed_at": cfg.get("indexed_at", ""),
            "files": counts.get("file", 0),
            "notes": counts.get("note", 0),
            "skipped": int(cfg.get("skipped", "0")),
            "local_only": True,
            "formats": sorted(SUPPORTED),
            "items": [
                dict(row)
                for row in self.store.db.execute(
                    "SELECT id,source,title,kind,created,LENGTH(body) AS characters FROM documents ORDER BY created DESC,title LIMIT 300"
                )
            ],
        }

    def document(self, document_id):
        row = self.store.db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise ValueError("Hujjat topilmadi. Ro'yxatni yangilang.")
        if row["kind"] == "file":
            root = self.settings().get("folder")
            path = (Path(root or "") / row["source"]).resolve()
            if not root or not path.is_relative_to(Path(root)) or not path.is_file():
                raise ValueError("Manba fayli topilmadi. Ulangan papkani yangilang.")
        return dict(row)

    @staticmethod
    def validate_folder(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Tanlangan papkaning to'liq yo'lini kiriting.")
        path = Path(value.strip().strip('"'))
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise ValueError("Mavjud mahalliy papkaning to'liq yo'lini kiriting.")
        path = path.resolve()
        if path == Path(path.anchor) or str(path).startswith("\\\\"):
            raise ValueError(
                "Diskning o'zi yoki tarmoq manzili o'rniga ichki mahalliy papkani tanlang."
            )
        return path

    async def index(self, value=None):
        root = self.validate_folder(value or self.settings().get("folder", ""))
        paths, skipped = await asyncio.to_thread(self._paths, root)
        rows = []
        size = 0
        for path in paths:
            try:
                if not path.resolve().is_relative_to(root) or path.is_symlink():
                    skipped += 1
                    continue
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "telegram_agent.document_extract",
                    str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                try:
                    async with asyncio.timeout(15):
                        output, _ = await process.communicate()
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                result = json.loads(output)
                body = result.get("text", "").strip()
                if not body or len(output) > 600000:
                    skipped += 1
                    continue
                size += len(body)
                if size > 4_000_000:
                    skipped += 1
                    break
                rows.append(
                    (
                        uuid.uuid4().hex,
                        str(path.relative_to(root)),
                        path.name,
                        body,
                        "file",
                        utc_now().isoformat(),
                    )
                )
            except (OSError, ValueError, TimeoutError):
                skipped += 1
        with self.store.db:
            self.store.db.execute("DELETE FROM documents WHERE kind='file'")
            self.store.db.executemany("INSERT INTO documents VALUES(?,?,?,?,?,?)", rows)
            self.store.db.executemany(
                "INSERT OR REPLACE INTO library_settings VALUES(?,?)",
                [
                    ("folder", str(root)),
                    ("indexed_at", utc_now().isoformat()),
                    ("skipped", str(skipped)),
                ],
            )
        return self.status()

    @staticmethod
    def _paths(root):
        paths, skipped, visited = [], 0, 0
        for parent, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and d.casefold() not in SKIP
                and not (Path(parent) / d).is_symlink()
                and (Path(parent) / d).resolve().is_relative_to(root)
            )
            for name in sorted(files):
                visited += 1
                if visited > 5000:
                    return paths, skipped + 1
                path = Path(parent) / name
                sensitive = any(
                    w in name.casefold()
                    for w in (
                        "password",
                        "credential",
                        "secret",
                        "api_key",
                        "session",
                        "parol",
                        "kalit",
                        "token",
                    )
                )
                if path.suffix.lower() not in SUPPORTED or name.startswith(".") or sensitive:
                    skipped += 1
                    continue
                try:
                    if path.stat().st_size > 5 * 1024 * 1024 or len(paths) >= 200:
                        skipped += 1
                        continue
                except OSError:
                    skipped += 1
                    continue
                paths.append(path)
        return paths, skipped

    def disconnect(self):
        with self.store.db:
            self.store.db.execute("DELETE FROM documents WHERE kind='file'")
            self.store.db.execute("DELETE FROM library_settings")
        return {"disconnected": True}

    def add_note(self, title, body):
        title = self.store._title(title)
        if not isinstance(body, str) or not body.strip() or len(body) > 10000:
            raise ValueError("Qayd 1..10000 belgidan iborat bo'lsin.")
        if self.status()["notes"] >= 100:
            raise ValueError("100 ta qayd chegarasiga yetildi.")
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    "Shaxsiy qayd",
                    title,
                    body.strip(),
                    "note",
                    utc_now().isoformat(),
                ),
            )
        return {"saved": True}

    def search(self, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise ValueError("Qidiruv 1..500 belgidan iborat bo'lsin.")
        terms = words(query)
        if not terms:
            raise ValueError("Mavzu, fayl nomi yoki qidiriladigan so'zni yozing.")
        root = self.settings().get("folder")
        results = []
        for row in self.store.db.execute("SELECT * FROM documents"):
            if row["kind"] == "file":
                path = (Path(root or "") / row["source"]).resolve()
                if not root or not path.is_relative_to(Path(root)) or not path.is_file():
                    continue
            title_score = (
                sum(t in (row["title"] + " " + row["source"]).casefold() for t in terms) * 2
            )
            best = None
            for offset in range(0, len(row["body"]), 1000):
                snippet = row["body"][offset : offset + 1200]
                score = title_score + sum(t in snippet.casefold() for t in terms)
                if score and (best is None or score > best[0]):
                    best = (score, snippet, offset)
            if best:
                results.append(
                    {
                        "source": row["source"],
                        "title": row["title"],
                        "snippet": best[1],
                        "offset": best[2],
                        "score": best[0],
                    }
                )
        return sorted(results, key=lambda r: -r["score"])[:5]

    def answer(self, query):
        rows = self.search(query)
        if not rows:
            return "Ulangan hujjat va qaydlardan mos parcha topilmadi. Boshqa kalit so'z yoki fayl nomini yozing."
        return "Mahalliy hujjatlardan topilgan parchalar (AI xulosasi emas):\n\n" + "\n\n".join(
            f"[{i + 1}] {r['title']} — {r['source']}\n{r['snippet']}"
            for i, r in enumerate(rows[:3])
        )
