import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


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
        """)
        # Additive migrations keep existing reminders, contacts and call history intact.
        for table, additions in {
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
        self.db.commit()

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
                "UPDATE reminders SET title=?,due=?,repeat=?,mode=?,attempts=0,retry_after=NULL,last_error=NULL WHERE id=? AND state='pending'",
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

    def reserve_call(self, user_id, cooldown_seconds=60, max_per_hour=3, now=None):
        now = now or utc_now()
        with self.db:
            row = self.db.execute(
                "SELECT created FROM call_attempts ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row and now - datetime.fromisoformat(row[0]) < timedelta(seconds=cooldown_seconds):
                return False
            count = self.db.execute(
                "SELECT COUNT(*) FROM call_attempts WHERE created>?",
                ((now - timedelta(hours=1)).isoformat(),),
            ).fetchone()[0]
            if count >= max_per_hour:
                return False
            self.db.execute(
                "INSERT INTO call_attempts(user_id,created) VALUES(?,?)", (user_id, now.isoformat())
            )
        return True

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
        query = query.casefold().strip()
        return [
            row
            for row in self.list_contacts()
            if query in (row["name"] + " " + row["reference"]).casefold()
        ][:30]

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
    ):
        if mode not in {"relay", "ask", "conversation", "record", "voice"} or language not in {
            "uz",
            "en",
            "ru",
        }:
            raise ValueError("Qo'ng'iroq turi yoki tili noto'g'ri.")
        if delivery not in {"call", "message"} or (delivery == "message" and mode != "voice"):
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
            "AND state IN ('queued','running') AND due IS ? AND mode=? AND language=? AND audio_id IS ? AND delivery=? AND collect_reply=? ORDER BY id LIMIT 1",
            (
                target.strip(),
                message.strip(),
                due,
                mode,
                language,
                audio_id,
                delivery,
                int(collect_reply),
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
                "note": "Bu topshiriq allaqachon navbatda yoki bajarilmoqda; takrorlanmadi.",
            }
        if (
            self.db.execute("SELECT COUNT(*) FROM outbound_calls WHERE state='queued'").fetchone()[
                0
            ]
            >= 10
        ):
            raise ValueError("Navbatda 10 ta topshiriq bor. Avval ularning yakunlanishini kuting.")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO outbound_calls(target,message,created,due,recipient_user_id,mode,language,max_turns,duration_seconds,audio_id,delivery,collect_reply) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
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

    def queue_notification(self, owner_id, body):
        digest = hashlib.sha256((str(owner_id) + "|" + body).encode()).hexdigest()
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO owner_outbox(id,owner_id,body,created,retry_after) VALUES(?,?,?,?,?)",
                (
                    digest,
                    owner_id,
                    body[:12000],
                    utc_now().isoformat(),
                    (utc_now() + timedelta(minutes=2)).isoformat(),
                ),
            )

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

    def list_contact_calls(self):
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
                "SELECT * FROM outbound_calls WHERE state='queued' AND (due IS NULL OR due<=?) ORDER BY COALESCE(due,created),id LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if row:
                self.db.execute(
                    "UPDATE outbound_calls SET state='running' WHERE id=?", (row["id"],)
                )
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
                "UPDATE outbound_calls SET state='interrupted',result='Agent qayta ishga tushdi; qayta terilmadi.' WHERE state='running'"
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
                "SELECT r.*,c.state AS task_state,c.answer_verified,c.message AS question FROM recordings r LEFT JOIN outbound_calls c ON c.id=r.job_id ORDER BY r.created DESC LIMIT 30"
            )
        ]

    def recover_recordings(self):
        with self.db:
            self.db.execute("UPDATE recordings SET state='captured' WHERE state='capturing'")
            self.db.execute("UPDATE recordings SET state='ready' WHERE state='sending'")

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
