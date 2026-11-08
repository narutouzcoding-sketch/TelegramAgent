"""Local AI test console: transient data, terminal reminders and call previews only."""

import asyncio
import sys
import tempfile
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path

from openai import APIError

from .ai_access import AIUnavailable, public_ai_error
from .brain import Brain
from .config import ROOT
from .scheduler import Scheduler
from .store import Store, utc_now

HELP = """SINOV rejimi: savol bering yoki reja/eslatma qo'shishni ayting.
/plans — sinov rejalari; /reminders — sinov eslatmalari
/calls — qo'ng'iroq topshirig'i qanday tushunilganini ko'rish
/demo — 3 soniyadan keyin terminalda eslatish (AI so'rovisiz)
/say MATN — tanlangan ovoz xizmatini sinash (OpenAI rejimida API xarajati bor)
/exit — chiqish; sinov bazasi o'chiriladi
Telegram ulanmaydi, hech kimga qo'ng'iroq qilinmaydi. AI so'rovlari tanlangan xizmatga yuboriladi."""


class SandboxStore(Store):
    def queue_contact_call(self, target, message, **options):
        result = super().queue_contact_call(target, message, **options)
        with self.db:
            self.db.execute(
                "UPDATE outbound_calls SET state='simulated',result=? WHERE id=?",
                ("Faqat sinov: real qo'ng'iroq yo'q.", result["id"]),
            )
        return {
            **result,
            "queued": False,
            "simulated": True,
            "status": "simulated",
            "note": "Faqat vaqtinchalik sinov bazasidagi oldindan ko'rish. Real navbat yaratilmagan.",
        }


class SandboxBrain(Brain):
    @property
    def contact_calls_available(self):
        return True  # The isolated store can only create previews, never active call jobs.

    def instructions(self):
        return super().instructions() + (
            " LOCAL SANDBOX: data is temporary and deleted on exit. Reminders appear only in "
            "this terminal. Calls are previews, never real or queued for later. Clearly label "
            "actions as tests; never promise Telegram delivery or a real call."
        )


@asynccontextmanager
async def session(settings, brain_factory=SandboxBrain):
    parent = (ROOT / "data").resolve()
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sandbox-", dir=parent) as folder:
        if Path(folder).resolve().parent != parent:
            raise ValueError("Sinov papkasi data/ ichida bo'lishi kerak.")
        store = SandboxStore(Path(folder) / "test.sqlite3", settings.timezone)
        brain = None
        try:
            brain = brain_factory(settings, store)
            yield brain, store
        finally:
            try:
                if brain:
                    await brain.close()
            finally:
                store.close()


async def read_console(prompt):
    if sys.platform != "win32" or not sys.stdin.isatty():
        return await asyncio.to_thread(input, prompt)
    import msvcrt

    print(prompt, end="", flush=True)
    characters = []
    while True:
        if not msvcrt.kbhit():
            await asyncio.sleep(0.03)
            continue
        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            msvcrt.getwch()
        elif char == "\x03":
            raise KeyboardInterrupt
        elif char == "\x1a":
            raise EOFError
        elif char in {"\r", "\n"}:
            print()
            return "".join(characters)
        elif char == "\b":
            if characters:
                characters.pop()
                print("\b \b", end="", flush=True)
        elif char.isprintable():
            characters.append(char)
            print(char, end="", flush=True)


def error_text(error):
    return (
        public_ai_error(error)
        if isinstance(error, (APIError, AIUnavailable))
        else type(error).__name__
    )


async def make_speech(brain, text, write=print):
    if not text.strip():
        write("Misol: /say Salom, men AI yordamchiman.")
        return False
    output = ROOT / "data" / "sandbox-voice.ogg"
    try:
        await brain.speech(text[:500], output)
    except Exception as error:
        write("Ovoz sinovi: " + error_text(error))
        return False
    write("Mahalliy ovoz fayli: " + str(output))
    return True


async def self_test(settings, speech=False, write=print, delay=2, brain_factory=SandboxBrain):
    write("Telegramdan mustaqil sinov. Matn AI: " + settings.resolved_text_provider)
    async with session(settings, brain_factory) as (brain, store):
        try:
            reply = await brain.answer(
                "Sinov rejamga '15 daqiqa kitob o'qish' ni qo'sh. Eslatma yoki qo'ng'iroq yaratma."
            )
        except Exception as error:
            write("AI + reja sinovi: " + error_text(error))
            return False
        plans = store.list_plans()
        plan_ok = (
            len(plans) == 1 and "kitob" in (plans[0]["title"] + " " + plans[0]["details"]).lower()
        )
        write("AI + reja sinovi: " + ("PASS" if plan_ok else "FAIL"))
        if not plan_ok:
            write("AI javobi: " + reply)
            write("Sinov bazasidagi reja soni: " + str(len(plans)))
        delivered = []

        async def delivery(row, late):
            delivered.append(row["id"])
            write("Terminal eslatmasi: " + row["title"])
            return "sandbox_console"

        reminder = store.add_reminder(
            "Sinov eslatmasi", (utc_now() + timedelta(seconds=delay)).isoformat(), mode="message"
        )
        await asyncio.sleep(delay + 0.03)
        await Scheduler(store, delivery).tick()
        reminder_ok = delivered == [reminder["id"]]
        write("Eslatma vaqti sinovi: " + ("PASS" if reminder_ok else "FAIL"))
        preview = store.queue_contact_call("@example", "Bu faqat sinov.")
        call_ok = preview["simulated"] and store.claim_contact_call() is None
        write(
            "Qo'ng'iroq oldindan ko'rish: " + ("PASS; real qo'ng'iroq yo'q" if call_ok else "FAIL")
        )
        speech_ok = (
            await make_speech(brain, "Salom! Men shaxsiy AI yordamchingizman.", write)
            if speech
            else True
        )
        write("Sinov tugadi. Real rejalar va Telegram o'zgarmadi; vaqtinchalik baza o'chiriladi.")
        return plan_ok and reminder_ok and call_ok and speech_ok


async def console(settings, read=read_console, write=print, brain_factory=SandboxBrain):
    write(HELP)
    write("Matn AI: " + settings.resolved_text_provider)
    async with session(settings, brain_factory) as (brain, store):

        async def delivery(row, late):
            write("\n[SINOV ESLATMA] " + row["title"] + " — faqat shu terminalda.")
            return "sandbox_console"

        worker = asyncio.create_task(Scheduler(store, delivery).run())
        try:
            while True:
                try:
                    text = (await read("Siz > ")).strip()
                except EOFError:
                    break
                if text.lower() in {"/exit", "/quit"}:
                    break
                if not text:
                    continue
                if text == "/help":
                    write(HELP)
                elif text == "/plans":
                    write(
                        "\n".join(
                            f"#{row['id']} {row['title']} — {row['details']}"
                            for row in store.list_plans()
                        )
                        or "Sinov rejasi yo'q."
                    )
                elif text == "/reminders":
                    write(
                        "\n".join(
                            f"#{row['id']} {row['title']} — {row['due_local']}"
                            for row in store.list_reminders()
                        )
                        or "Sinov eslatmasi yo'q."
                    )
                elif text == "/calls":
                    write(
                        "\n".join(
                            f"[SIMULYATSIYA] #{row['id']} {row['target']} — {row['message']}"
                            for row in store.list_contact_calls()
                        )
                        or "Sinov qo'ng'iroq topshirig'i yo'q."
                    )
                elif text == "/demo":
                    store.add_reminder(
                        "Uch soniyalik eslatma",
                        (utc_now() + timedelta(seconds=3)).isoformat(),
                        mode="message",
                    )
                    write("3 soniyalik terminal eslatmasi qo'yildi.")
                elif text.startswith("/say ") or text == "/say":
                    await make_speech(brain, text[4:].strip(), write)
                else:
                    try:
                        write("Agent > " + await brain.answer(text[:12000]))
                    except Exception as error:
                        write("Agent > " + error_text(error))
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
    write("Sinov tugadi. Vaqtinchalik rejalar, eslatmalar va suhbat o'chirildi.")
