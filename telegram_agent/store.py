import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def utc_now():
    return datetime.now(UTC)


def parse_due(value: str, timezone: str, now=None):
    due = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if due.tzinfo is None:
        due = due.replace(tzinfo=ZoneInfo(timezone))
    due = due.astimezone(UTC)
    if due <= (now or utc_now()):
        raise ValueError("Eslatma vaqti kelajakda bo'lishi kerak. Sana va vaqtni aniqlashtiring.")
    return due


class Store:
    def __init__(self, path: Path, timezone="Asia/Tashkent"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.timezone = timezone
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, due TEXT NOT NULL,
            repeat TEXT NOT NULL, mode TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, lease_until TEXT,
            last_error TEXT, retry_after TEXT, delivery_status TEXT, created TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS reminder_due ON reminders(state, due);
          CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', created TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS tool_results (
            call_id TEXT PRIMARY KEY, result TEXT NOT NULL
          );
        """)

    def add_reminder(self, title, due_at, repeat="none", mode="call"):
        title = self._title(title)
        if repeat not in {"none", "daily", "weekly"} or mode not in {"call", "message"}:
            raise ValueError("Noto'g'ri repeat yoki mode.")
        due = parse_due(due_at, self.timezone)
        with self.db:
            cur = self.db.execute(
                "INSERT INTO reminders(title,due,repeat,mode,created) VALUES(?,?,?,?,?)",
                (title, due.isoformat(), repeat, mode, utc_now().isoformat()),
            )
        return {
            "id": cur.lastrowid,
            "title": title,
            "due_at": due.astimezone(ZoneInfo(self.timezone)).isoformat(),
            "repeat": repeat,
            "mode": mode,
            "saved": True,
        }

    def list_reminders(self):
        rows = self.db.execute(
            "SELECT * FROM reminders WHERE state IN ('pending','delivering') ORDER BY due LIMIT 100"
        ).fetchall()
        return [
            dict(row)
            | {
                "due_local": datetime.fromisoformat(row["due"])
                .astimezone(ZoneInfo(self.timezone))
                .isoformat()
            }
            for row in rows
        ]

    def cancel_reminder(self, reminder_id):
        with self.db:
            n = self.db.execute(
                "UPDATE reminders SET state='cancelled' WHERE id=? AND state IN ('pending','delivering')",
                (reminder_id,),
            ).rowcount
        return {"cancelled": bool(n), "id": reminder_id}

    def claim_due(self, now=None):
        now = now or utc_now()
        # A lease allows recovery after an interrupted delivery. Run only one agent process.
        with self.db:
            self.db.execute(
                "UPDATE reminders SET state='pending' WHERE state='delivering' AND lease_until<=?",
                (now.isoformat(),),
            )
            row = self.db.execute(
                "SELECT * FROM reminders WHERE state='pending' AND due<=? "
                "AND (retry_after IS NULL OR retry_after<=?) ORDER BY due LIMIT 1",
                (now.isoformat(), now.isoformat()),
            ).fetchone()
            if row is None:
                return None
            self.db.execute(
                "UPDATE reminders SET state='delivering',attempts=attempts+1,lease_until=? WHERE id=?",
                ((now + timedelta(minutes=65)).isoformat(), row["id"]),
            )
        return dict(row)

    def finish(self, row, error=None, now=None, delivery_status=None):
        now = now or utc_now()
        with self.db:
            current = self.db.execute(
                "SELECT state FROM reminders WHERE id=?", (row["id"],)
            ).fetchone()
            if current is None or current["state"] == "cancelled":
                return
            if error:
                attempts = row["attempts"] + 1
                state = "failed" if attempts >= 3 else "pending"
                retry_at = now + timedelta(minutes=2 * attempts)
                self.db.execute(
                    "UPDATE reminders SET state=?,retry_after=?,last_error=?,lease_until=NULL WHERE id=?",
                    (state, retry_at.isoformat(), error[:120], row["id"]),
                )
            elif row["repeat"] == "none":
                self.db.execute(
                    "UPDATE reminders SET state='delivered',lease_until=NULL,delivery_status=? WHERE id=?",
                    (delivery_status, row["id"]),
                )
            else:
                due = datetime.fromisoformat(row["due"]).astimezone(ZoneInfo(self.timezone))
                step = timedelta(days=1 if row["repeat"] == "daily" else 7)
                while due.astimezone(UTC) <= now:
                    due += step
                self.db.execute(
                    "UPDATE reminders SET state='pending',due=?,attempts=0,lease_until=NULL,"
                    "last_error=NULL,retry_after=NULL,delivery_status=? WHERE id=?",
                    (due.astimezone(UTC).isoformat(), delivery_status, row["id"]),
                )

    def add_plan(self, title, details=""):
        with self.db:
            cur = self.db.execute(
                "INSERT INTO plans(title,details,created) VALUES(?,?,?)",
                (self._title(title), str(details)[:4000], utc_now().isoformat()),
            )
        return {"saved": True, "id": cur.lastrowid}

    def list_plans(self):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM plans WHERE status='open' ORDER BY id DESC LIMIT 100"
            )
        ]

    def complete_plan(self, plan_id):
        with self.db:
            n = self.db.execute(
                "UPDATE plans SET status='done' WHERE id=? AND status='open'", (plan_id,)
            ).rowcount
        return {"completed": bool(n), "id": plan_id}

    def remember(self, role, text):
        if text.strip():
            with self.db:
                self.db.execute(
                    "INSERT INTO messages(role,content,created) VALUES(?,?,?)",
                    (role, text[:12000], utc_now().isoformat()),
                )
                self.db.execute(
                    "DELETE FROM messages WHERE id NOT IN "
                    "(SELECT id FROM messages ORDER BY id DESC LIMIT 200)"
                )

    def history(self, limit=20):
        rows = self.db.execute(
            "SELECT role,content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def cached_tool(self, call_id):
        row = self.db.execute(
            "SELECT result FROM tool_results WHERE call_id=?", (call_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_tool(self, call_id, result):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO tool_results VALUES(?,?)",
                (call_id, json.dumps(result, ensure_ascii=False)),
            )

    @staticmethod
    def _title(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise ValueError("Sarlavha 1..500 belgidan iborat bo'lishi kerak.")
        return value.strip()

    def close(self):
        self.db.close()
