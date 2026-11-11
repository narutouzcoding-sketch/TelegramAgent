import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REMINDER_DRAFT_KEY = "local_reminder_draft"


def utc_now():
    return datetime.now(UTC)


def parse_due(value: str, timezone: str, now=None):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Sana va vaqtni kiriting, masalan 2026-12-01T09:00.")
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
        self.root = path.parent.parent if path.parent.name == "data" else path.parent
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.create_function(
            "casefold", 1, lambda value: (value or "").casefold(), deterministic=True
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS reminder_failures (id INTEGER PRIMARY KEY,reminder_id INTEGER NOT NULL,due TEXT NOT NULL,error TEXT NOT NULL,created TEXT NOT NULL)"
        )
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
          CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, reference TEXT NOT NULL UNIQUE
          );
          CREATE TABLE IF NOT EXISTS outbound_calls (
            id INTEGER PRIMARY KEY, target TEXT NOT NULL, message TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued', result TEXT, created TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS telegram_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS call_attempts (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS call_attempts_created ON call_attempts(created);
        """)
        # Additive migrations keep existing reminders, contacts and call history intact.
        for table, additions in {
            "reminders": {
                "recovery_message_only": "INTEGER NOT NULL DEFAULT 0",
                "claim_token": "TEXT",
                "message_random_id": "INTEGER",
                "message_confirmed": "INTEGER NOT NULL DEFAULT 0",
                "snoozed_from": "INTEGER",
            },
            "contacts": {
                "telegram_id": "INTEGER",
                "call_allowed": "INTEGER NOT NULL DEFAULT 0",
                "source": "TEXT NOT NULL DEFAULT 'manual'",
            },
            "outbound_calls": {
                "answer_verified": "INTEGER NOT NULL DEFAULT 0",
                "answer_evidence": "TEXT NOT NULL DEFAULT '[]'",
                "question_delivered": "INTEGER NOT NULL DEFAULT 0",
                "diagnostics": "TEXT NOT NULL DEFAULT '{}'",
                "audio_id": "TEXT",
                "delivery": "TEXT NOT NULL DEFAULT 'call'",
                "collect_reply": "INTEGER NOT NULL DEFAULT 0",
                "due": "TEXT",
                "recipient_user_id": "INTEGER",
                "mode": "TEXT NOT NULL DEFAULT 'relay'",
                "language": "TEXT NOT NULL DEFAULT 'uz'",
                "max_turns": "INTEGER NOT NULL DEFAULT 4",
                "duration_seconds": "INTEGER NOT NULL DEFAULT 180",
                "transcript": "TEXT NOT NULL DEFAULT '[]'",
                "summary": "TEXT NOT NULL DEFAULT ''",
                "fallback_to_message": "INTEGER NOT NULL DEFAULT 0",
                "text_random_id": "INTEGER",
                "text_message_id": "INTEGER",
                "text_sent_at": "TEXT",
                "text_body": "TEXT NOT NULL DEFAULT ''",
            },
        }.items():
            columns = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
            for name, declaration in additions.items():
                if name not in columns:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        self.db.commit()

        # Older versions treated raw audio/greetings as completed answers. Keep
        # their recordings/history, but do not present unverified results as success.
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET state=CASE WHEN mode='record' THEN 'recorded_unverified' ELSE 'answer_unverified' END,result='Oldingi natijada savolga javob olingani tekshirilmagan.',summary='Javob tasdiqlanmagan. ' || COALESCE(summary,'') WHERE state='completed' AND answer_verified=0"
            )
        message_columns = {r[1] for r in self.db.execute("PRAGMA table_info(messages)")}
        if "private" not in message_columns:
            self.db.execute("ALTER TABLE messages ADD COLUMN private INTEGER NOT NULL DEFAULT 0")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS voice_assets (id TEXT PRIMARY KEY,label TEXT NOT NULL,filename TEXT NOT NULL,duration REAL NOT NULL,created TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS contact_exclusions (digest TEXT PRIMARY KEY)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS owner_outbox (id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,retry_after TEXT,last_error TEXT NOT NULL DEFAULT '')"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS recordings (id TEXT PRIMARY KEY, peer_id INTEGER, label TEXT, job_id INTEGER, created TEXT, state TEXT, filename TEXT DEFAULT '',incoming_filename TEXT DEFAULT '', duration REAL DEFAULT 0, attempts INTEGER DEFAULT 0,retry_after TEXT,last_error TEXT DEFAULT '')"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS contact_text_replies (job_id INTEGER NOT NULL,message_id INTEGER NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(job_id,message_id))"
        )
        self.db.commit()

        # A timeout before any media is not an ASR error and has no call recording.
        from .call_outcomes import connection_outcome

        old = self.db.execute(
            "SELECT id,diagnostics,transcript FROM outbound_calls c WHERE state='failed' AND result='TimedOutAnswer' AND question_delivered=0 AND NOT EXISTS(SELECT 1 FROM recordings r WHERE r.job_id=c.id)"
        ).fetchall()
        for row in old:
            try:
                diagnostic = json.loads(row["diagnostics"])
                transcript = json.loads(row["transcript"])
                if (
                    diagnostic.get("connected")
                    or diagnostic.get("playback_frames")
                    or diagnostic.get("input_frames")
                    or any(t.get("role") == "user" for t in transcript)
                ):
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
            state, report = connection_outcome("TimedOutAnswer")
            diagnostic.update(
                stage=state, connected=False, recording_started=False, error_code="TimedOutAnswer"
            )
            with self.db:
                self.db.execute(
                    "UPDATE outbound_calls SET state=?,result=?,summary=?,diagnostics=? WHERE id=?",
                    (
                        state,
                        report[:200],
                        report,
                        json.dumps(diagnostic, ensure_ascii=False),
                        row["id"],
                    ),
                )

        old_limits = self.db.execute(
            """SELECT id,diagnostics,transcript FROM outbound_calls c
               WHERE state='failed' AND result LIKE ? AND question_delivered=0
               AND NOT EXISTS(SELECT 1 FROM recordings r WHERE r.job_id=c.id)""",
            ("Mahalliy qo'ng'iroq chegarasiga yetildi.%",),
        ).fetchall()
        for row in old_limits:
            try:
                diagnostic = json.loads(row["diagnostics"])
                transcript = json.loads(row["transcript"])
                if (
                    diagnostic.get("error_code") != "TelegramPaused"
                    or diagnostic.get("connected")
                    or diagnostic.get("telegram_accepted")
                    or diagnostic.get("playback_frames")
                    or diagnostic.get("input_frames")
                    or any(turn.get("role") == "user" for turn in transcript)
                ):
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
            report = "Mahalliy qo'ng'iroq limiti sabab telefon terilmagan."
            diagnostic["error_code"] = "CallRateLimited"
            with self.db:
                self.db.execute(
                    "UPDATE outbound_calls SET state='rate_limited',result=?,summary=?,diagnostics=? WHERE id=?",
                    (report, report, json.dumps(diagnostic, ensure_ascii=False), row["id"]),
                )

    def add_reminder(self, title, due_at, repeat="none", mode="call", *, draft=None):
        title = self._title(title)
        if repeat not in {"none", "daily", "weekly"} or mode not in {"call", "message"}:
            raise ValueError("Noto'g'ri repeat yoki mode.")
        due = parse_due(due_at, self.timezone)
        with self.db:
            if (
                draft is not None
                and not self.db.execute(
                    "DELETE FROM telegram_state WHERE key=? AND value=?",
                    (REMINDER_DRAFT_KEY, draft),
                ).rowcount
            ):
                raise ValueError("Qoralama o'zgardi. /eslatma bilan qayta boshlang.")
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
            "SELECT * FROM reminders WHERE state IN ('pending','delivering','failed') ORDER BY due LIMIT 100"
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
                "UPDATE reminders SET state='cancelled' WHERE id=? AND state IN ('pending','delivering','failed')",
                (reminder_id,),
            ).rowcount
        return {"cancelled": bool(n), "id": reminder_id}

    def snooze_reminder(self, reminder_id, minutes=15, *, request_id=None, now=None):
        if type(reminder_id) is not int or reminder_id < 1:
            raise ValueError("Eslatmaning raqamli ID sini kiriting.")
        if type(minutes) is not int or not 1 <= minutes <= 10080:
            raise ValueError("Kechiktirish 1..10080 daqiqa orasida bo'lsin.")
        if request_id is not None and (
            not isinstance(request_id, str) or not 1 <= len(request_id) <= 100
        ):
            raise ValueError("So'rov identifikatori noto'g'ri.")
        now = now or utc_now()
        due = now + timedelta(minutes=minutes)
        key = "snooze:" + request_id if request_id else None
        arguments = {"reminder_id": reminder_id, "minutes": minutes}
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            cached = self.cached_tool(key) if key else None
            if cached:
                if cached["arguments"] != arguments:
                    raise ValueError("Bu identifikator boshqa eslatish so'roviga tegishli.")
                return cached["result"]
            source = self.db.execute(
                "SELECT * FROM reminders WHERE id=?", (reminder_id,)
            ).fetchone()
            if source is None or source["state"] == "cancelled":
                raise ValueError("Faol yoki yetkazilgan eslatma topilmadi.")
            if source["state"] == "delivering":
                raise ValueError("Eslatma hozir yetkazilmoqda. Tugagach keyinga suring.")
            target_id = reminder_id
            if source["repeat"] != "none":
                copy = self.db.execute(
                    "SELECT id,state FROM reminders WHERE snoozed_from=? AND state IN ('pending','failed','delivering') ORDER BY id DESC LIMIT 1",
                    (reminder_id,),
                ).fetchone()
                if copy and copy["state"] == "delivering":
                    raise ValueError(
                        "Qo'shimcha eslatma hozir yetkazilmoqda. Tugagach keyinga suring."
                    )
                if copy:
                    target_id = copy["id"]
                else:
                    target_id = self.db.execute(
                        "INSERT INTO reminders(title,due,repeat,mode,created,snoozed_from) VALUES(?,?,'none','message',?,?)",
                        (source["title"], due.isoformat(), now.isoformat(), reminder_id),
                    ).lastrowid
                next_due = datetime.fromisoformat(source["due"]).astimezone(ZoneInfo(self.timezone))
                step = timedelta(days=1 if source["repeat"] == "daily" else 7)
                while next_due.astimezone(UTC) <= due:
                    next_due += step
                self.db.execute(
                    """UPDATE reminders SET due=?,state='pending',attempts=0,retry_after=NULL,
                       lease_until=NULL,claim_token=NULL,message_random_id=NULL,message_confirmed=0,
                       recovery_message_only=0,last_error=NULL WHERE id=?""",
                    (next_due.astimezone(UTC).isoformat(), reminder_id),
                )
            self.db.execute(
                """UPDATE reminders SET due=?,mode='message',state='pending',attempts=0,retry_after=NULL,
                   lease_until=NULL,claim_token=NULL,message_random_id=NULL,message_confirmed=0,
                   recovery_message_only=0,last_error=NULL,delivery_status=NULL WHERE id=?""",
                (due.isoformat(), target_id),
            )
            result = {
                "saved": True,
                "id": target_id,
                "source_id": reminder_id,
                "title": source["title"],
                "due_at": due.astimezone(ZoneInfo(self.timezone)).isoformat(),
                "mode": "message",
            }
            if key:
                self.db.execute(
                    "INSERT INTO tool_results VALUES(?,?)",
                    (key, json.dumps({"arguments": arguments, "result": result})),
                )
        return result

    def daily_overview(self, now=None):
        local = (now or utc_now()).astimezone(ZoneInfo(self.timezone))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()
        end = (
            (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
            .astimezone(UTC)
            .isoformat()
        )
        now_utc = local.astimezone(UTC).isoformat()
        reminder_counts = self.db.execute(
            """SELECT COUNT(*) total,COALESCE(SUM(due<?),0) overdue,COALESCE(SUM(state='failed'),0) failed
               FROM reminders WHERE state IN ('pending','delivering','failed') AND due<?""",
            (now_utc, end),
        ).fetchone()
        reminders = [
            dict(row)
            for row in self.db.execute(
                """SELECT id,title,due,state,mode FROM reminders
               WHERE state IN ('pending','delivering','failed') AND due<? ORDER BY due,id LIMIT 10""",
                (end,),
            )
        ]
        for row in reminders:
            row["due_local"] = (
                datetime.fromisoformat(row["due"]).astimezone(ZoneInfo(self.timezone)).isoformat()
            )
        tasks = [
            dict(row)
            for row in self.db.execute(
                """SELECT id,target,state,result,COALESCE(due,created) due FROM outbound_calls
               WHERE (state IN ('queued','running') AND COALESCE(due,created)<?)
               OR (created>=? AND created<? AND state IN ('failed','text_failed','interrupted','rate_limited','text_replied'))
               ORDER BY created DESC,id DESC LIMIT 10""",
                (end, start, end),
            )
        ]
        return {
            "date": local.date().isoformat(),
            "timezone": self.timezone,
            "open_plans": self.db.execute(
                "SELECT COUNT(*) FROM plans WHERE status='open'"
            ).fetchone()[0],
            "reminder_counts": dict(reminder_counts),
            "plans": self.list_plans()[:5],
            "reminders": reminders,
            "tasks": tasks,
        }

    def search_local(self, query):
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError("Qidirish matni 1..200 belgidan iborat bo'lsin.")
        needle = query.strip().casefold()
        rows = self.db.execute(
            """WITH records AS (
               SELECT 'plan' kind,id,title,details snippet,status state,created at FROM plans
               UNION ALL SELECT 'reminder',id,title,due,state,created FROM reminders
               UNION ALL SELECT 'contact',id,name,reference,'saved','' FROM contacts
               UNION ALL SELECT 'task',id,target,message||' '||COALESCE(summary,''),state,created FROM outbound_calls)
               SELECT kind,id,title,substr(snippet,1,400) snippet,state,at FROM records
               WHERE instr(casefold(COALESCE(title,'')||' '||COALESCE(snippet,'')),?)>0 ORDER BY at DESC,id DESC LIMIT 30""",
            (needle,),
        ).fetchall()
        return [dict(row) for row in rows]

    def retry_reminder(self, reminder_id):
        with self.db:
            changed = self.db.execute(
                "UPDATE reminders SET state='pending',recovery_message_only=1,attempts=0,retry_after=NULL,last_error=NULL,lease_until=NULL WHERE id=? AND state='failed'",
                (reminder_id,),
            ).rowcount
        if not changed:
            raise ValueError("Qayta yuborish uchun xatoli eslatma topilmadi.")
        return {"queued": True, "id": reminder_id, "mode": "message"}

    def recover_reminders(self, now=None, all_inflight=False):
        now = now or utc_now()
        with self.db:
            self.db.execute(
                "UPDATE reminders SET state='pending',recovery_message_only=1,attempts=0,lease_until=NULL,retry_after=NULL,last_error='Oldingi yetkazish uzilgan; yetkazilgani tasdiqlanmagan.' WHERE state='delivering' AND (? OR lease_until<=?)",
                (int(all_inflight), now.isoformat()),
            )

    def claim_due(self, now=None):
        now = now or utc_now()
        # A lease allows recovery after an interrupted delivery. Run only one agent process.
        self.recover_reminders(now)
        with self.db:
            row = self.db.execute(
                """UPDATE reminders SET state='delivering',attempts=attempts+1,lease_until=?,
                   claim_token=?,message_random_id=COALESCE(message_random_id,?)
                   WHERE id=(SELECT id FROM reminders WHERE state='pending' AND due<=?
                   AND (retry_after IS NULL OR retry_after<=?) ORDER BY due,id LIMIT 1)
                   RETURNING *""",
                (
                    (now + timedelta(minutes=65)).isoformat(),
                    secrets.token_hex(16),
                    secrets.randbits(63) or 1,
                    now.isoformat(),
                    now.isoformat(),
                ),
            ).fetchone()
            if row is None:
                return None
        return dict(row) | {"attempts": row["attempts"] - 1}

    def confirm_reminder_message(self, row):
        with self.db:
            return bool(
                self.db.execute(
                    "UPDATE reminders SET message_confirmed=1 WHERE id=? AND state='delivering' AND claim_token=?",
                    (row["id"], row["claim_token"]),
                ).rowcount
            )

    def finish(self, row, error=None, now=None, delivery_status=None):
        now = now or utc_now()
        with self.db:
            if not self.db.execute(
                "UPDATE reminders SET claim_token=NULL WHERE id=? AND state='delivering' AND claim_token=?",
                (row["id"], row["claim_token"]),
            ).rowcount:
                return
            if error:
                attempts = row["attempts"] + 1
                if attempts >= 3:
                    self.db.execute(
                        "INSERT INTO reminder_failures(reminder_id,due,error,created) VALUES(?,?,?,?)",
                        (row["id"], row["due"], error[:120], now.isoformat()),
                    )
                if attempts >= 3 and row["repeat"] != "none":
                    due = datetime.fromisoformat(row["due"]).astimezone(ZoneInfo(self.timezone))
                    step = timedelta(days=1 if row["repeat"] == "daily" else 7)
                    while due.astimezone(UTC) <= now:
                        due += step
                    self.db.execute(
                        "UPDATE reminders SET state='pending',due=?,attempts=0,lease_until=NULL,retry_after=NULL,recovery_message_only=0,message_random_id=NULL,message_confirmed=0,last_error=?,delivery_status='previous_occurrence_failed' WHERE id=?",
                        (due.astimezone(UTC).isoformat(), error[:120], row["id"]),
                    )
                    return
                state = "failed" if attempts >= 3 else "pending"
                retry_at = now + timedelta(minutes=2 * attempts)
                self.db.execute(
                    "UPDATE reminders SET state=?,retry_after=?,last_error=?,lease_until=NULL,recovery_message_only=1 WHERE id=?",
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
                    "last_error=NULL,retry_after=NULL,recovery_message_only=0,message_random_id=NULL,message_confirmed=0,delivery_status=? WHERE id=?",
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

    def workspace_overview(self):
        return {
            "recording_counts": dict(
                self.db.execute("SELECT state,COUNT(*) FROM recordings GROUP BY state")
            ),
            "recording_seconds": self.db.execute(
                "SELECT COALESCE(SUM(duration),0) FROM recordings"
            ).fetchone()[0],
            "plan_counts": dict(
                self.db.execute("SELECT status,COUNT(*) FROM plans GROUP BY status")
            ),
            "completed_plans": [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM plans WHERE status='done' ORDER BY id DESC LIMIT 100"
                )
            ],
            "reminder_counts": dict(
                self.db.execute("SELECT state,COUNT(*) FROM reminders GROUP BY state")
            ),
            "reminder_history": [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM reminders WHERE state IN ('delivered','cancelled') ORDER BY due DESC LIMIT 100"
                )
            ],
            "contact_activity": {
                str(row["recipient_user_id"]): {"count": row["count"], "last": row["last"]}
                for row in self.db.execute(
                    "SELECT recipient_user_id,COUNT(*) count,MAX(created) last FROM outbound_calls WHERE recipient_user_id IS NOT NULL GROUP BY recipient_user_id"
                )
            },
        }

    def complete_plan(self, plan_id):
        with self.db:
            n = self.db.execute(
                "UPDATE plans SET status='done' WHERE id=? AND status='open'", (plan_id,)
            ).rowcount
        return {"completed": bool(n), "id": plan_id}

    def update_plan(self, plan_id, title, details=""):
        with self.db:
            count = self.db.execute(
                "UPDATE plans SET title=?,details=? WHERE id=? AND status='open'",
                (self._title(title), str(details)[:4000], plan_id),
            ).rowcount
        if not count:
            raise ValueError("Ochiq reja topilmadi.")
        return {"saved": True, "id": plan_id}

    def update_reminder(self, reminder_id, title, due_at, repeat="none", mode="message"):
        title = self._title(title)
        due = parse_due(due_at, self.timezone)
        if repeat not in {"none", "daily", "weekly"} or mode not in {"call", "message"}:
            raise ValueError("Noto'g'ri repeat yoki mode.")
        with self.db:
            count = self.db.execute(
                "UPDATE reminders SET state='pending',recovery_message_only=0,title=?,due=?,repeat=?,mode=?,attempts=0,retry_after=NULL,last_error=NULL,message_random_id=NULL,message_confirmed=0 WHERE id=? AND state IN ('pending','failed')",
                (title, due.isoformat(), repeat, mode, reminder_id),
            ).rowcount
        if not count:
            raise ValueError("Kutilayotgan eslatma topilmadi yoki hozir yetkazilmoqda.")
        return {"saved": True, "id": reminder_id}

    def remember(self, role, text, private=False):
        if text.strip():
            with self.db:
                self.db.execute(
                    "INSERT INTO messages(role,content,created,private) VALUES(?,?,?,?)",
                    (role, text[:12000], utc_now().isoformat(), int(bool(private))),
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

    def context(self, limit=10, max_chars=10000):
        rows = self.db.execute(
            "SELECT role,content FROM messages WHERE private=0 ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        entries = [dict(row) for row in reversed(rows)]
        retained = []
        size = 0
        for entry in reversed(entries):
            if size + len(entry["content"]) > max_chars:
                break
            retained.append(entry)
            size += len(entry["content"])
        retained.reverse()
        while retained and retained[0]["role"] != "user":
            retained.pop(0)
        return retained

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

    def telegram_state(self, key):
        row = self.db.execute("SELECT value FROM telegram_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_telegram_state(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO telegram_state VALUES(?,?)", (key, value))

    def next_call_at(self, cooldown_seconds, max_per_hour, now=None):
        now = now or utc_now()
        attempts = self.db.execute(
            "SELECT created FROM call_attempts ORDER BY created DESC LIMIT ?", (max_per_hour,)
        ).fetchall()
        if not attempts:
            return None
        earliest = datetime.fromisoformat(attempts[0][0]) + timedelta(seconds=cooldown_seconds)
        if len(attempts) == max_per_hour:
            earliest = max(earliest, datetime.fromisoformat(attempts[-1][0]) + timedelta(hours=1))
        return earliest if earliest > now else None

    def call_limit_message(self, retry_at):
        local = retry_at.astimezone(ZoneInfo(self.timezone))
        if local.microsecond:
            local += timedelta(seconds=1)
        return f"Mahalliy qo'ng'iroq limiti band. Telefon terilmadi. {local:%Y-%m-%d %H:%M:%S} ({self.timezone}) dan keyin yangi topshiriq bering."

    def call_budget(self, cooldown_seconds, max_per_hour, now=None):
        now = now or utc_now()
        used = self.db.execute(
            "SELECT COUNT(*) FROM call_attempts WHERE created>?",
            ((now - timedelta(hours=1)).isoformat(),),
        ).fetchone()[0]
        retry_at = self.next_call_at(cooldown_seconds, max_per_hour, now)
        text = (
            f"Oxirgi 60 daqiqada {used}/{max_per_hour} qo'ng'iroq urinishi. "
            f"Urinishlar oralig'i kamida {cooldown_seconds} soniya."
        )
        if retry_at:
            text += " " + self.call_limit_message(retry_at)
        else:
            text += " Hozir mahalliy limit bo'yicha qo'ng'iroq mumkin."
        return {
            "used": used,
            "remaining": max(0, max_per_hour - used),
            "max_per_hour": max_per_hour,
            "cooldown_seconds": cooldown_seconds,
            "retry_at": retry_at.isoformat() if retry_at else None,
            "text": text,
        }

    def reserve_call_slot(self, user_id, cooldown_seconds, max_per_hour, now=None):
        now = now or utc_now()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if retry_at := self.next_call_at(cooldown_seconds, max_per_hour, now):
                return retry_at
            self.db.execute(
                "INSERT INTO call_attempts(user_id,created) VALUES(?,?)", (user_id, now.isoformat())
            )
        return None

    def reserve_call(self, user_id, cooldown_seconds=60, max_per_hour=3, now=None):
        return self.reserve_call_slot(user_id, cooldown_seconds, max_per_hour, now) is None

    def save_contact(self, name, reference):
        name = self._title(name)
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 200:
            raise ValueError("Kontakt uchun @username yoki to'liq telefon raqami kerak.")
        with self.db:
            self.db.execute(
                "INSERT INTO contacts(name,reference) VALUES(?,?) "
                "ON CONFLICT(reference) DO UPDATE SET name=excluded.name",
                (name, reference.strip()),
            )
        return {"saved": True, "name": name}

    def list_contacts(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM contacts ORDER BY name")]

    def search_contacts(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Qidirish uchun ism yoki username kiriting.")
        from .contact_names import contact_matches

        return [row for row in self.list_contacts() if contact_matches(row, query)][:30]

    def import_contacts(self, contacts, source="telegram"):
        added = skipped = 0
        with self.db:
            for row in contacts:
                reference = str(row.get("reference", "")).strip()
                user_id = row.get("telegram_id")
                identifiers = (reference.casefold(), str(user_id or ""))
                if not reference or any(
                    self.db.execute(
                        "SELECT 1 FROM contact_exclusions WHERE digest=?",
                        (hashlib.sha256(v.encode()).hexdigest(),),
                    ).fetchone()
                    for v in identifiers
                    if v
                ):
                    skipped += 1
                    continue
                existing = self.db.execute(
                    "SELECT id FROM contacts WHERE reference=? OR (telegram_id IS NOT NULL AND telegram_id=?)",
                    (reference, user_id),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                self.db.execute(
                    "INSERT INTO contacts(name,reference,telegram_id,source) VALUES(?,?,?,?)",
                    (self._title(row.get("name") or reference), reference, user_id, source),
                )
                added += 1
        return {"imported": added, "skipped": skipped, "total": len(self.list_contacts())}

    def set_contact_permission(self, contact_id, telegram_id, allowed):
        if telegram_id is not None and (not isinstance(telegram_id, int) or telegram_id <= 0):
            raise ValueError("Kontaktning Telegram ID si noto'g'ri.")
        if allowed and not telegram_id:
            raise ValueError("Avval kontaktning Telegram akkauntini tekshiring.")
        with self.db:
            count = self.db.execute(
                "UPDATE contacts SET telegram_id=?,call_allowed=? WHERE id=?",
                (telegram_id, int(bool(allowed)), contact_id),
            ).rowcount
        if not count:
            raise ValueError("Kontakt topilmadi.")
        return {"saved": True, "id": contact_id}

    def approved_contact_ids(self):
        return tuple(
            row[0]
            for row in self.db.execute(
                "SELECT DISTINCT telegram_id FROM contacts WHERE call_allowed=1 AND telegram_id IS NOT NULL"
            )
        )

    def delete_contact(self, contact_id):
        with self.db:
            row = self.db.execute(
                "SELECT reference,telegram_id FROM contacts WHERE id=?", (contact_id,)
            ).fetchone()
            if row:
                for value in row:
                    if value:
                        self.db.execute(
                            "INSERT OR IGNORE INTO contact_exclusions VALUES(?)",
                            (hashlib.sha256(str(value).casefold().encode()).hexdigest(),),
                        )
            count = self.db.execute("DELETE FROM contacts WHERE id=?", (contact_id,)).rowcount
        return {"deleted": bool(count)}

    def queue_contact_call(
        self,
        target,
        message,
        due_at=None,
        recipient_user_id=None,
        mode="relay",
        language="uz",
        max_turns=4,
        duration_seconds=180,
        audio_id=None,
        delivery="call",
        collect_reply=False,
        *,
        call_limits=None,
        fallback_to_message=False,
    ):
        if mode not in {
            "relay",
            "ask",
            "conversation",
            "record",
            "voice",
            "text",
        } or language not in {
            "uz",
            "en",
            "ru",
        }:
            raise ValueError("Qo'ng'iroq turi yoki tili noto'g'ri.")
        if type(fallback_to_message) is not bool:
            raise ValueError("Xabar zaxirasi true yoki false bo'lsin.")
        if mode == "text":
            delivery = "message"
        if delivery not in {"call", "message"} or (
            delivery == "message" and mode not in {"voice", "text"}
        ):
            raise ValueError("Yetkazish turi noto'g'ri.")
        if type(collect_reply) is not bool or (
            collect_reply and (mode != "voice" or delivery != "call")
        ):
            raise ValueError("Javob yozish faqat asl ovozli qo'ng'iroq uchun.")
        if mode == "voice":
            if not isinstance(audio_id, str) or not self.voice_asset(audio_id):
                raise ValueError("Avval asl ovoz yozuvini saqlang yoki tanlang.")
        elif audio_id is not None:
            raise ValueError("Asl ovoz uchun voice rejimini tanlang.")
        if (
            not isinstance(max_turns, int)
            or not 1 <= max_turns <= 10
            or not isinstance(duration_seconds, int)
            or not 30 <= duration_seconds <= 600
        ):
            raise ValueError("Suhbat 1..10 javob va 30..600 soniya orasida bo'lsin.")
        if not isinstance(target, str) or not target.strip() or len(target) > 200:
            raise ValueError("Aniq kontakt ismi, @username yoki +mamlakat_kodi bilan raqam kerak.")
        if not isinstance(message, str) or not message.strip() or len(message) > 1500:
            raise ValueError("Yetkaziladigan gap 1..1500 belgidan iborat bo'lishi kerak.")
        from .call_intent import effective_call_mode

        mode = effective_call_mode(message, mode)
        due = parse_due(due_at, self.timezone).isoformat() if due_at else None
        existing = self.db.execute(
            "SELECT id,state FROM outbound_calls WHERE target=? AND message=? "
            "AND state IN ('queued','running') AND due IS ? AND mode=? AND language=? AND audio_id IS ? AND delivery=? AND collect_reply=? AND fallback_to_message=? ORDER BY id LIMIT 1",
            (
                target.strip(),
                message.strip(),
                due,
                mode,
                language,
                audio_id,
                delivery,
                int(collect_reply),
                int(fallback_to_message),
            ),
        ).fetchone()
        if existing:
            return {
                "queued": True,
                "id": existing["id"],
                "target": target.strip(),
                "message": message.strip(),
                "status": existing["state"],
                "duplicate_suppressed": True,
                "mode": mode,
                "delivery": delivery,
                "fallback_to_message": fallback_to_message,
                "note": "Bu topshiriq allaqachon navbatda yoki bajarilmoqda; takrorlanmadi.",
            }
        if (
            delivery == "call"
            and not fallback_to_message
            and due is None
            and call_limits is not None
        ):
            if retry_at := self.next_call_at(*call_limits):
                raise ValueError(self.call_limit_message(retry_at))
        if (
            self.db.execute("SELECT COUNT(*) FROM outbound_calls WHERE state='queued'").fetchone()[
                0
            ]
            >= 10
        ):
            raise ValueError("Navbatda 10 ta topshiriq bor. Avval ularning yakunlanishini kuting.")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO outbound_calls(target,message,created,due,recipient_user_id,mode,language,max_turns,duration_seconds,audio_id,delivery,collect_reply,fallback_to_message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    target.strip(),
                    message.strip(),
                    utc_now().isoformat(),
                    due,
                    recipient_user_id,
                    mode,
                    language,
                    max_turns,
                    duration_seconds,
                    audio_id,
                    delivery,
                    int(collect_reply),
                    int(fallback_to_message),
                ),
            )
        return {
            "queued": True,
            "id": cursor.lastrowid,
            "target": target.strip(),
            "message": message.strip(),
            "status": "queued",
            "due_at": due,
            "channel": "telegram",
            "mode": mode,
            "language": language,
            "delivery": delivery,
            "fallback_to_message": fallback_to_message,
            "audio_id": audio_id,
            "collect_reply": collect_reply,
            "note": "Siz bilan faol qo'ng'iroq tugagach bajariladi. Hali yetkazilmadi.",
        }

    def add_voice_asset(self, asset_id, label, duration):
        with self.db:
            self.db.execute(
                "INSERT INTO voice_assets(id,label,filename,duration,created) VALUES(?,?,?,?,?)",
                (asset_id, self._title(label), asset_id + ".ogg", duration, utc_now().isoformat()),
            )

    def voice_asset(self, asset_id):
        row = self.db.execute(
            "SELECT * FROM voice_assets WHERE id=? AND archived=0", (asset_id,)
        ).fetchone()
        return dict(row) if row else None

    def voice_assets(self):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM voice_assets WHERE archived=0 ORDER BY created DESC LIMIT 100"
            )
        ]

    def archive_voice_asset(self, asset_id):
        with self.db:
            if self.db.execute(
                "SELECT 1 FROM outbound_calls WHERE audio_id=? AND state IN ('queued','running')",
                (asset_id,),
            ).fetchone():
                raise ValueError(
                    "Bu ovoz navbatdagi vazifada ishlatilmoqda. Avval vazifani bekor qiling."
                )
            self.db.execute("UPDATE voice_assets SET archived=1 WHERE id=?", (asset_id,))
        return {"archived": True}

    def _queue_notification(self, owner_id, body, delay_seconds=120):
        digest = hashlib.sha256((str(owner_id) + "|" + body).encode()).hexdigest()
        return self.db.execute(
            "INSERT OR IGNORE INTO owner_outbox(id,owner_id,body,created,retry_after) VALUES(?,?,?,?,?)",
            (
                digest,
                owner_id,
                body[:12000],
                utc_now().isoformat(),
                (utc_now() + timedelta(seconds=delay_seconds)).isoformat(),
            ),
        ).rowcount

    def queue_notification(self, owner_id, body):
        with self.db:
            self._queue_notification(owner_id, body)

    def begin_contact_text(self, job_id, recipient_id, body):
        with self.db:
            row = self.db.execute(
                """UPDATE outbound_calls SET recipient_user_id=?,text_body=?,text_random_id=?
                   WHERE id=? AND state='running' AND text_random_id IS NULL RETURNING text_random_id""",
                (recipient_id, body, secrets.randbits(63) or 1, job_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    "Ushbu xabar yuborish bosqichi allaqachon boshlangan yoki bekor qilingan."
                )
        return row[0]

    def finish_contact_text(self, job_id, owner_id, state, report, message_id=None):
        if state not in {"text_sent", "text_failed", "interrupted"}:
            raise ValueError("Noto'g'ri matnli xabar holati.")
        with self.db:
            changed = self.db.execute(
                """UPDATE outbound_calls SET state=?,result=?,summary=?,text_message_id=?,text_sent_at=?
                   WHERE id=? AND state='running'""",
                (
                    state,
                    report[:200],
                    report[:6000],
                    message_id,
                    utc_now().isoformat() if state == "text_sent" else None,
                    job_id,
                ),
            ).rowcount
            if changed:
                self._queue_notification(owner_id, report, delay_seconds=0)
                self.db.execute(
                    "INSERT INTO messages(role,content,created,private) VALUES('assistant',?,?,1)",
                    (report, utc_now().isoformat()),
                )

    def capture_contact_text_reply(self, sender_id, reply_to_id, message_id, text, owner_id):
        with self.db:
            row = self.db.execute(
                """SELECT id,target FROM outbound_calls WHERE recipient_user_id=? AND text_message_id=?
                   AND state IN ('text_sent','text_replied') AND text_sent_at>=? ORDER BY id DESC LIMIT 1""",
                (sender_id, reply_to_id, (utc_now() - timedelta(hours=24)).isoformat()),
            ).fetchone()
            if row is None:
                return False
            count = self.db.execute(
                "SELECT COUNT(*) FROM contact_text_replies WHERE job_id=?", (row["id"],)
            ).fetchone()[0]
            if count >= 10:
                return False
            body = text[:3000] + (
                "\n[Javobning davomi Telegram chatida.]" if len(text) > 3000 else ""
            )
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO contact_text_replies VALUES(?,?,?,?)",
                (row["id"], message_id, body, utc_now().isoformat()),
            ).rowcount
            if not inserted:
                return False
            report = f"Vazifa #{row['id']}: {row['target']} dan yozma javob:\n{body}"
            self.db.execute(
                "UPDATE outbound_calls SET state='text_replied',result='Kontaktning yozma javobi keldi.',summary=? WHERE id=?",
                (report, row["id"]),
            )
            self._queue_notification(owner_id, report, delay_seconds=0)
            self.db.execute(
                "INSERT INTO messages(role,content,created,private) VALUES('assistant',?,?,1)",
                (report, utc_now().isoformat()),
            )
        return True

    def pending_notification(self, owner_id):
        row = self.db.execute(
            "SELECT * FROM owner_outbox WHERE owner_id=? AND state='pending' AND (retry_after IS NULL OR retry_after<=?) AND attempts<3 ORDER BY created LIMIT 1",
            (owner_id, utc_now().isoformat()),
        ).fetchone()
        return dict(row) if row else None

    def finish_notification(self, notification_id, error=None):
        with self.db:
            if error:
                self.db.execute(
                    "UPDATE owner_outbox SET attempts=attempts+1,state=CASE WHEN attempts>=2 THEN 'failed' ELSE 'pending' END,retry_after=?,last_error=? WHERE id=?",
                    ((utc_now() + timedelta(minutes=5)).isoformat(), error[:100], notification_id),
                )
            else:
                self.db.execute(
                    "UPDATE owner_outbox SET state='sent',last_error='' WHERE id=?",
                    (notification_id,),
                )

    def notification_status(self, owner_id):
        return dict(
            self.db.execute(
                "SELECT state,COUNT(*) FROM owner_outbox WHERE owner_id=? AND state<>'sent' GROUP BY state",
                (owner_id,),
            )
        )

    def retry_notifications(self, owner_id):
        with self.db:
            count = self.db.execute(
                "UPDATE owner_outbox SET state='pending',attempts=0,retry_after=NULL WHERE owner_id=? AND state='failed'",
                (owner_id,),
            ).rowcount
        return {"queued": count}

    def list_contact_calls(self, *, include_active=False):
        if include_active:
            return [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM outbound_calls WHERE state IN ('queued','running') OR id IN (SELECT id FROM outbound_calls ORDER BY id DESC LIMIT 20) ORDER BY id DESC"
                )
            ]
        return [
            dict(row)
            for row in self.db.execute("SELECT * FROM outbound_calls ORDER BY id DESC LIMIT 20")
        ]

    def cancel_contact_call(self, job_id):
        with self.db:
            changed = self.db.execute(
                "UPDATE outbound_calls SET state='cancelled' WHERE id=? AND state='queued'",
                (job_id,),
            ).rowcount
        return {
            "cancelled": bool(changed),
            "id": job_id,
            "note": "Faol qo'ng'iroqni /hangup bilan to'xtating.",
        }

    def claim_contact_call(self, now=None):
        now = now or utc_now()
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET state='cancelled',result=? WHERE state='queued' AND due IS NOT NULL AND due<?",
                (
                    "Belgilangan vaqtdan 5 daqiqa o'tdi; qayta terilmadi.",
                    (now - timedelta(minutes=5)).isoformat(),
                ),
            )
            row = self.db.execute(
                """UPDATE outbound_calls SET state='running' WHERE id=(
                   SELECT id FROM outbound_calls WHERE state='queued' AND (due IS NULL OR due<=?)
                   ORDER BY COALESCE(due,created),id LIMIT 1) RETURNING *""",
                (now.isoformat(),),
            ).fetchone()
        return dict(row) if row else None

    def finish_contact_call(self, job_id, state, result):
        if state not in {
            "sent",
            "failed",
            "cancelled",
            "interrupted",
            "completed",
            "no_answer",
            "recorded_unverified",
            "answer_unverified",
            "partial_answer",
            "declined",
            "unanswered",
            "busy",
            "rejected",
            "privacy_blocked",
            "connection_failed",
            "rate_limited",
            "text_sent",
            "text_failed",
            "text_replied",
        }:
            raise ValueError("Noto'g'ri qo'ng'iroq holati")
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET state=?,result=? WHERE id=?",
                (state, result[:200], job_id),
            )

    def save_contact_report(
        self,
        job_id,
        transcript,
        summary,
        *,
        answer_verified=False,
        answer_evidence=(),
        question_delivered=False,
        diagnostics=None,
    ):
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET transcript=?,summary=?,answer_verified=?,answer_evidence=?,question_delivered=?,diagnostics=? WHERE id=?",
                (
                    json.dumps(transcript[:22], ensure_ascii=False),
                    summary[:6000],
                    int(bool(answer_verified)),
                    json.dumps(list(answer_evidence)[:10], ensure_ascii=False),
                    int(bool(question_delivered)),
                    json.dumps(diagnostics or {}, ensure_ascii=False),
                    job_id,
                ),
            )

    def recover_contact_calls(self):
        # Do not repeat a call that might already have reached a third party.
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET state='interrupted',result=CASE WHEN text_random_id IS NOT NULL THEN 'Xabar yuborish uzilgan; yetkazilgani tasdiqlanmagan.' ELSE 'Agent qayta ishga tushdi; qayta terilmadi.' END WHERE state='running'"
            )
            self.db.execute(
                "UPDATE outbound_calls SET state='cancelled',result='Topshiriq 10 daqiqadan ortiq eskirgan.' WHERE state='queued' AND COALESCE(due,created)<?",
                ((utc_now() - timedelta(minutes=10)).isoformat(),),
            )

    def start_recording(self, recording_id, peer_id, label, job_id):
        with self.db:
            self.db.execute(
                "INSERT INTO recordings(id,peer_id,label,job_id,created,state) VALUES(?,?,?,?,?,'capturing')",
                (recording_id, peer_id, str(label)[:200], job_id, utc_now().isoformat()),
            )

    def recording_captured(self, recording_id, duration):
        with self.db:
            self.db.execute(
                "UPDATE recordings SET state='captured',duration=? WHERE id=?",
                (duration, recording_id),
            )

    def recording_ready(self, recording_id, filename, incoming_filename, duration):
        with self.db:
            self.db.execute(
                "UPDATE recordings SET state='ready',filename=?,incoming_filename=?,duration=?,last_error='' WHERE id=?",
                (filename, incoming_filename, duration, recording_id),
            )

    def recording_failed(self, recording_id, error):
        with self.db:
            self.db.execute(
                "UPDATE recordings SET state='failed',last_error=? WHERE id=?",
                (error[:300], recording_id),
            )

    def pending_recordings(self, state):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM recordings WHERE state=? ORDER BY created LIMIT 50", (state,)
            )
        ]

    def list_recordings(self):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT r.*,c.state AS task_state,c.answer_verified,c.message AS question,c.summary,c.transcript FROM recordings r LEFT JOIN outbound_calls c ON c.id=r.job_id ORDER BY r.created DESC LIMIT 30"
            )
        ]

    def recover_recordings(self):
        with self.db:
            self.db.execute("UPDATE recordings SET state='captured' WHERE state='capturing'")
            self.db.execute(
                "UPDATE recordings SET state=CASE WHEN attempts>=3 THEN 'failed' ELSE 'ready' END,last_error='Yuborish uzilgan; yetkazilgani tasdiqlanmagan. Qayta yuborishda nusxa kelishi mumkin.' WHERE state='sending'"
            )

    def claim_recording(self):
        with self.db:
            row = self.db.execute(
                "SELECT * FROM recordings WHERE state='ready' AND (retry_after IS NULL OR retry_after<=?) AND attempts<3 ORDER BY created LIMIT 1",
                (utc_now().isoformat(),),
            ).fetchone()
            if row:
                self.db.execute(
                    "UPDATE recordings SET state='sending',attempts=attempts+1 WHERE id=?",
                    (row["id"],),
                )
        return dict(row) if row else None

    def recording_sent(self, recording_id):
        with self.db:
            self.db.execute(
                "UPDATE recordings SET state='sent',last_error='' WHERE id=?", (recording_id,)
            )

    def recording_retry(self, recording_id, error):
        with self.db:
            self.db.execute(
                "UPDATE recordings SET state=CASE WHEN attempts>=3 THEN 'failed' ELSE 'ready' END,retry_after=?,last_error=? WHERE id=?",
                ((utc_now() + timedelta(minutes=2)).isoformat(), error[:200], recording_id),
            )

    def retry_recording(self, recording_id):
        with self.db:
            row = self.db.execute(
                "SELECT filename,state FROM recordings WHERE id=?", (recording_id,)
            ).fetchone()
            if not row:
                raise ValueError("Ovoz yozuvi topilmadi.")
            if row["state"] in {"capturing", "sending", "captured"}:
                raise ValueError(
                    "Ovoz yozuvi hozir tayyorlanyapti yoki yuborilyapti. Tugashini kuting."
                )
            state = "ready" if row["filename"] else "captured"
            self.db.execute(
                "UPDATE recordings SET state=?,attempts=0,retry_after=NULL WHERE id=?",
                (state, recording_id),
            )
        return {"queued": True}
