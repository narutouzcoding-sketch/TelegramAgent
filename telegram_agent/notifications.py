"""Retry owner reports only, never recipient calls or third-party messages."""

import asyncio

from .telegram_policy import TelegramPaused


async def deliver_pending(app):
    row = app.store.pending_notification(app.settings.owner_id)
    if row is None:
        return False
    try:
        await app.send_text(row["body"])
    except TelegramPaused:
        raise
    except Exception as exc:
        app.store.finish_notification(row["id"], type(exc).__name__)
    else:
        app.store.finish_notification(row["id"])
    return True


async def run_notifications(app):
    while True:
        await deliver_pending(app)
        await asyncio.sleep(5)
