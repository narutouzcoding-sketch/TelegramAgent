import asyncio
import logging
from datetime import datetime, timedelta

from .store import utc_now

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, store, delivery, grace_hours=24):
        self.store = store
        self.delivery = delivery
        self.grace_hours = grace_hours

    async def tick(self):
        row = self.store.claim_due()
        if not row:
            return False
        late = utc_now() - datetime.fromisoformat(row["due"]) > timedelta(hours=self.grace_hours)
        try:
            # Very old reminders become messages instead of unexpected stale calls.
            result = await self.delivery(row, late)
        except asyncio.CancelledError:
            self.store.finish(row, error="interrupted")
            raise
        except Exception as exc:
            log.warning("Reminder delivery failed id=%s type=%s", row["id"], type(exc).__name__)
            self.store.finish(row, error=type(exc).__name__)
        else:
            self.store.finish(row, delivery_status=result)
        return True

    async def run(self):
        while True:
            if not await self.tick():
                await asyncio.sleep(2)
