import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .store import REMINDER_DRAFT_KEY

TIME_HINT = "Masalan: 15 daqiqa, ertaga 09:00 yoki 2026-12-01 09:00."
RELATIVE = re.compile(r"([1-9][0-9]{0,4})\s+(daqiqa|soat|kun)(?:dan keyin)?", re.IGNORECASE)
CLOCK = re.compile(r"(?:(bugun|ertaga)\s+)?([0-9]{1,2}):([0-9]{2})", re.IGNORECASE)
DATE_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt]| +)[0-9]{2}:[0-9]{2}")
SIMPLE_COMMAND = re.compile(r"(menga xabar yubor|rejamga qo['’‘ʻʼ]?sh)\s*:\s*(.*)", re.IGNORECASE)


def due_time(text, now):
    text = text.strip()
    if match := RELATIVE.fullmatch(text):
        unit = {"daqiqa": "minutes", "soat": "hours", "kun": "days"}[match[2].casefold()]
        return now + timedelta(**{unit: int(match[1])})
    if match := CLOCK.fullmatch(text):
        day = now + timedelta(days=(match[1] or "").casefold() == "ertaga")
        return day.replace(hour=int(match[2]), minute=int(match[3]), second=0, microsecond=0)
    if DATE_TIME.fullmatch(text):
        return datetime.fromisoformat(" ".join(text.split())).replace(tzinfo=now.tzinfo)
    return None


def task_reply(store, text):
    text = text.strip()
    if match := SIMPLE_COMMAND.fullmatch(text):
        text = ("/xabar " if match[1].casefold().startswith("menga") else "/reja ") + match[2]
    parts = text.split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].casefold()
    content = parts[1].strip() if len(parts) > 1 else ""
    if command in {"/keyin", "/snooze"}:
        values = content.split(maxsplit=1)
        if not values or not values[0].isdecimal():
            return "Masalan /keyin 12 15 daqiqa. Eslatma ID sini /reminders bilan ko'ring."
        minutes = 15
        if len(values) > 1:
            delay = values[1].strip()
            match = RELATIVE.fullmatch(delay)
            if match:
                minutes = (
                    int(match[1]) * {"daqiqa": 1, "soat": 60, "kun": 1440}[match[2].casefold()]
                )
            elif delay.isdecimal():
                minutes = int(delay)
            else:
                return "Kechiktirish muddatini yozing. Masalan /keyin 12 15 daqiqa."
        try:
            saved = store.snooze_reminder(int(values[0]), minutes)
        except ValueError as exc:
            return str(exc)
        return f"Eslatma #{saved['id']} {saved['due_at']} da xabar bilan yuboriladi."
    if command in {"/done", "/bajarildi"}:
        if not content.isdecimal():
            return "Masalan /bajarildi 3. Reja ID sini /plans bilan ko'ring."
        result = store.complete_plan(int(content))
        return "Reja bajarildi deb belgilandi." if result["completed"] else "Ochiq reja topilmadi."
    if command in {"/reja", "/plan"}:
        if not content:
            return "Reja nomini kiriting. Masalan: /reja Kitob o'qish"
        try:
            plan = store.add_plan(content)
        except ValueError as exc:
            return str(exc)
        return f"#{plan['id']} reja saqlandi: {content}."

    if command == "/bekor":
        store.set_telegram_state(REMINDER_DRAFT_KEY, "")
        return "Eslatma qoralamasi bekor qilindi."

    now = datetime.now(ZoneInfo(store.timezone))
    if command in {"/eslatma", "/remind", "/xabar"}:
        title, _, timing = content.partition("|")
        title, timing = title.strip(), timing.strip()
        if not title:
            return f"Xabar matnini kiriting. Masalan: {command} Suv ichish"
        if len(title) > 500:
            return "Xabar matni 500 belgidan oshmasin."
        previous = store.telegram_state(REMINDER_DRAFT_KEY)
        draft = previous or None
    else:
        if not any(pattern.fullmatch(text.strip()) for pattern in (RELATIVE, CLOCK, DATE_TIME)):
            return None
        draft = store.telegram_state(REMINDER_DRAFT_KEY)
        if not draft:
            return None
        pending = json.loads(draft)
        if datetime.fromisoformat(pending["expires"]) <= now:
            return "Qoralama muddati tugadi. /eslatma bilan qayta boshlang."
        title, timing = pending["title"], text.strip()

    try:
        due = due_time(timing, now)
    except ValueError:
        due = None
    if due is None or due <= now:
        if command in {"/eslatma", "/remind", "/xabar"}:
            pending = json.dumps(
                {"title": title, "expires": (now + timedelta(minutes=15)).isoformat()}
            )
            store.set_telegram_state(REMINDER_DRAFT_KEY, pending)
            if not timing:
                return f"Qachon xabar yuboray? {TIME_HINT} Bekor qilish uchun /bekor."
        return f"Kelajakdagi sana va vaqtni kiriting. {TIME_HINT}"
    try:
        reminder = store.add_reminder(title, due.isoformat(), mode="message", draft=draft)
    except ValueError as exc:
        return str(exc)
    return f"#{reminder['id']} eslatma saqlandi. {due:%Y-%m-%d %H:%M} ({store.timezone}) da Telegram orqali sizga xabar yuboriladi."
