"""Disposable browser QA panel. No Telegram session, external AI or user data is opened."""

import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp import web  # noqa: E402

from telegram_agent.config import Settings  # noqa: E402
from telegram_agent.panel import PanelControl, create_panel  # noqa: E402


async def main():
    with tempfile.TemporaryDirectory(prefix="telegram-agent-browser-qa-") as directory:
        root = Path(directory)
        cfg = Settings(
            api_id=1,
            api_hash="qa-only",
            owner_id=42,
            openai_key="",
            voice_provider="free",
            enable_voice_calls=True,
        )
        control = PanelControl(cfg, root=root)
        tone = root / "tone.ogg"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2",
                "-c:a",
                "libopus",
                str(tone),
            ],
            check=True,
        )

        async def speech(text, path, **options):
            shutil.copyfile(tone, path)

        class Worker:
            def __init__(self, settings):
                self.settings = settings
                self.ready = asyncio.Event()
                self.call_lock = asyncio.Lock()
                self.owner_name = "SINOV AKKAUNTI — haqiqiy Telegram ulanmagan"
                self.policy = SimpleNamespace(ensure_active=lambda: None)
                self.brain = SimpleNamespace(
                    settings=settings,
                    answer=self.answer,
                    close=self.close,
                    speech=speech,
                    free_speech=SimpleNamespace(speech=speech),
                )

            async def run(self):
                self.ready.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.ready.clear()

            async def answer(self, text):
                control.store.remember("user", text)
                await asyncio.sleep(1)
                result = "SINOV: xabaringiz qabul qilindi. Bu haqiqiy AI javobi emas."
                control.store.remember("assistant", result)
                return result

            async def close(self):
                pass

            async def queue_requested_call(self, target, message, **options):
                row = control.store.queue_contact_call(target, message, **options)
                with control.store.db:
                    control.store.db.execute(
                        "UPDATE outbound_calls SET state='simulated',result='Faqat QA; terilmadi.' WHERE id=?",
                        (row["id"],),
                    )
                return row

        control.agent_factory = Worker
        control.store.save_contact("QA Kursdosh", "@qa_example")
        control.store.save_contact("QA Ikkinchi", "+998901234567")
        control.store.add_plan("SINOV: kitob o‘qish", "Vaqtinchalik QA bazasi")
        from telegram_agent.voice_library import save_upload

        await save_upload(
            control.store, tone.read_bytes(), "QA — o'zim yozgan ovoz o'rniga sun'iy signal"
        )
        documents = root / "qa-documents"
        documents.mkdir()
        (documents / "jadval.txt").write_text(
            "QA dars jadvali: Dushanba soat 09:00 da matematika.", encoding="utf-8"
        )
        await control.documents.index(str(documents))
        control.store.start_recording("a" * 32, 42, "QA — sun'iy signal", None)
        folder = root / "data" / "recordings"
        folder.mkdir(exist_ok=True)
        shutil.copyfile(tone, folder / "qa.ogg")
        control.store.recording_ready("a" * 32, "qa.ogg", "qa.ogg", 2)
        control.store.recording_sent("a" * 32)
        await control.start()
        app = create_panel(control, "Qa-Sinov-2026!")
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", 8766).start()
            print("QA only: http://127.0.0.1:8766 | password: Qa-Sinov-2026!", flush=True)
            await control.shutdown.wait()
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
