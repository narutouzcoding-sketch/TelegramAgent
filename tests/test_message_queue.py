import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram_agent.app import AgentApp
from telegram_agent.panel import PanelControl


async def test_following_telegram_message_is_queued_instead_of_discarded(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    app.message_lock = asyncio.Lock()
    app.send_text = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()
    seen = []

    async def process(event, text):
        seen.append(text)
        started.set()
        await release.wait()

    app.process_message = process

    def event(text):
        return SimpleNamespace(
            is_private=True,
            out=False,
            sender_id=42,
            raw_text=text,
            message=SimpleNamespace(contact=None),
        )

    task1 = asyncio.create_task(app.on_message(event("Birinchi savol")))
    await started.wait()
    task2 = asyncio.create_task(app.on_message(event("Keyingi savol")))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(task1, task2)
    assert seen == ["Birinchi savol", "Keyingi savol"]
    assert app.pending_messages == 0
    app.send_text.assert_not_called()


async def test_following_panel_message_waits_for_current_answer(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    gate = asyncio.Event()
    seen = []

    async def answer(text):
        seen.append(text)
        await gate.wait()
        return text

    control.idle_brain = SimpleNamespace(answer=answer, close=AsyncMock())
    try:
        first = asyncio.create_task(control.ask("first"))
        await asyncio.sleep(0)
        second = asyncio.create_task(control.ask("second"))
        await asyncio.sleep(0)
        gate.set()
        assert await asyncio.gather(first, second) == [{"reply": "first"}, {"reply": "second"}]
        assert seen == ["first", "second"]
    finally:
        await control.close()
