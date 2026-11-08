"""Persistent local usage; never stores prompts, audio, contact data or keys."""

import json
import math
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .ai_access import AIUnavailable


def estimate_input(instructions, messages, tools):
    """Conservative reservation, not a provider tokenizer or billing guarantee."""
    text = len(instructions) + len(json.dumps(tools, ensure_ascii=False))
    audio = 0
    for message in messages:
        content = message.get("content", "") or ""
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "input_audio":
                    # Our input is mono16k PCM16 WAV. No base64 retained in the ledger.
                    seconds = len(part.get("input_audio", {}).get("data", "")) * 0.75 / 32000
                    audio += math.ceil(seconds * 32)
                else:
                    text += len(json.dumps(part, ensure_ascii=False))
        else:
            text += len(str(content))
    return math.ceil(text / 2) + audio


class UsageLedger:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        with store.db:
            store.db.execute(
                "CREATE TABLE IF NOT EXISTS ai_usage (id TEXT PRIMARY KEY,day TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,purpose TEXT NOT NULL,state TEXT NOT NULL,reserved INTEGER NOT NULL,input_tokens INTEGER,output_tokens INTEGER,created TEXT NOT NULL)"
            )
            store.db.execute("CREATE INDEX IF NOT EXISTS ai_usage_day ON ai_usage(day,provider)")

    def day(self, now=None):
        return (
            (now or datetime.now(timezone.utc))
            .astimezone(ZoneInfo(self.settings.timezone))
            .date()
            .isoformat()
        )

    def reserve(self, provider, model, purpose, estimated, now=None):
        now = now or datetime.now(timezone.utc)
        day = self.day(now)
        key = uuid.uuid4().hex
        # Lock across independent panel/worker connections before checking the cap.
        db = self.store.db
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(COALESCE(input_tokens+output_tokens,reserved)),0) FROM ai_usage WHERE day=? AND provider=?",
                (day, provider),
            ).fetchone()
            requests = getattr(self.settings, "ai_daily_max_requests", 0)
            tokens = getattr(self.settings, "ai_daily_max_tokens", 0)
            if provider != "local" and (
                (requests and row[0] >= requests) or (tokens and row[1] + estimated > tokens)
            ):
                raise AIUnavailable(
                    "Mahalliy kunlik AI sarf chegarasiga yetildi. Tayyor mahalliy model yoki tokensiz amallardan foydalaning."
                )
            db.execute(
                "INSERT INTO ai_usage VALUES(?,?,?,?,?, 'pending', ?,NULL,NULL,?)",
                (key, day, provider, model, purpose, estimated, now.isoformat()),
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return key

    def finish(self, key, response=None, state="ok"):
        usage = getattr(response, "usage", None)
        incoming = getattr(usage, "prompt_tokens", None)
        outgoing = getattr(usage, "completion_tokens", None)
        with self.store.db:
            self.store.db.execute(
                "UPDATE ai_usage SET state=?,input_tokens=?,output_tokens=? WHERE id=?",
                (state, incoming, outgoing, key),
            )

    def summary(self):
        day = self.day()
        rows = self.store.db.execute(
            "SELECT provider,COUNT(*) AS requests,COALESCE(SUM(input_tokens),0) AS input_tokens,COALESCE(SUM(output_tokens),0) AS output_tokens,SUM(input_tokens IS NULL) AS unknown_usage,COALESCE(SUM(CASE WHEN input_tokens IS NULL THEN reserved ELSE 0 END),0) AS unconfirmed_reserved FROM ai_usage WHERE day=? GROUP BY provider",
            (day,),
        ).fetchall()
        return {
            "day": day,
            "timezone": self.settings.timezone,
            "providers": {r["provider"]: dict(r) for r in rows},
            "max_requests": getattr(self.settings, "ai_daily_max_requests", 0),
            "max_tokens": getattr(self.settings, "ai_daily_max_tokens", 0),
        }
