"""Content-free VoIP tracing and Telethon exported-sender compatibility repair."""

import logging
import time

from telethon.tl import types

log = logging.getLogger(__name__)


def forward_exported_updates(client, observer=None):
    """Keep CALL_MIGRATE accepted/signaling updates on the existing client queue.

    PyTgCalls borrows Telethon senders for migrated phone RPCs. Telethon creates
    these without an updates queue. The native receive loop otherwise drops
    PhoneCallAccepted with None.put_nowait, even though the peer picked up.
    No extra authorization/session, request, retry or credential is introduced.
    """
    if getattr(client, "_agent_exported_updates_installed", False):
        return
    original = client._borrow_exported_sender

    async def borrow(dc_id):
        sender = await original(dc_id)
        if getattr(sender, "_updates_queue", None) is None:
            sender._updates_queue = client._updates_queue
            log.info("Forwarded Telegram exported sender updates dc=%s", dc_id)
            if observer:
                observer(dc_id)
        return sender

    client._borrow_exported_sender = borrow
    client._agent_exported_updates_installed = True


class CallSignals:
    def __init__(self, own_id):
        self.own_id = own_id
        self.peer_id = self.call_id = None
        self.started = time.monotonic()
        self.metrics = {}
        self.events = []

    def begin(self, peer_id, metrics, job_id=None):
        self.peer_id, self.call_id = peer_id, None
        self.started = time.monotonic()
        self.metrics, self.events = metrics, []
        self.metrics.update(
            job_id=job_id,
            telegram_accepted=False,
            telegram_confirmed=False,
            signal_events=self.events,
        )

    def mark(self, kind, **data):
        if self.peer_id is None:
            return
        if len(self.events) < 30:
            self.events.append(
                {"kind": kind, "after_ms": round((time.monotonic() - self.started) * 1000), **data}
            )

    def exported(self, dc_id):
        if self.peer_id is not None:
            self.metrics["exported_updates_forwarded"] = True
            self.mark("exported_updates_forwarded", dc=dc_id)

    async def observe(self, update):
        if self.peer_id is None:
            return
        if isinstance(update, types.UpdatePhoneCallSignalingData):
            if update.phone_call_id == self.call_id:
                self.metrics["signaling_received"] = self.metrics.get("signaling_received", 0) + 1
            return
        if not isinstance(update, types.UpdatePhoneCall):
            return
        call = update.phone_call
        if isinstance(call, types.PhoneCallDiscarded):
            if call.id == self.call_id:
                self.mark("discarded", reason=type(call.reason).__name__)
            return
        admin, participant = getattr(call, "admin_id", None), getattr(call, "participant_id", None)
        peer = (
            participant if admin == self.own_id else admin if participant == self.own_id else None
        )
        if peer != self.peer_id:
            return
        self.call_id = call.id
        if isinstance(call, types.PhoneCallAccepted):
            self.metrics["telegram_accepted"] = True
            self.metrics["stage"] = "accepted_waiting_media"
            self.mark("accepted")
        elif isinstance(call, types.PhoneCall):
            self.metrics["telegram_confirmed"] = True
            self.mark("confirmed")
        elif isinstance(call, types.PhoneCallWaiting):
            self.mark("waiting", device_reached=bool(call.receive_date))
        elif isinstance(call, types.PhoneCallRequested):
            self.mark("requested")

    def snapshot(self):
        return dict(self.metrics)

    def end(self):
        self.mark("ended")
        self.metrics["ended"] = True
        self.peer_id = self.call_id = None


def trace_phone_rpc(calls, signals):
    """Observe migrated DC and RPC stage without recording request payloads."""
    bridge = calls._app._bind_client
    original = bridge._invoke

    async def invoke(request, dc_id=None, chat_id=None, sleep_threshold=None):
        phone = request.__class__.__module__ == "telethon.tl.functions.phone"
        if phone:
            signals.mark(
                "phone_rpc", method=type(request).__name__, dc=dc_id or bridge._app.session.dc_id
            )
        try:
            result = await original(request, dc_id, chat_id, sleep_threshold)
            if phone and hasattr(result, "phone_call"):
                await signals.observe(types.UpdatePhoneCall(result.phone_call))
            return result
        except Exception as exc:
            if phone:
                signals.mark(
                    "phone_rpc_error", method=type(request).__name__, error=type(exc).__name__
                )
            raise

    bridge._invoke = invoke
    native = getattr(calls, "_handle_connection_changed", None)
    if native is not None:

        async def changed(peer, info):
            if peer == signals.peer_id:
                signals.mark(
                    "native_connection", state=getattr(info.state, "name", str(info.state))
                )
            return await native(peer, info)

        calls._handle_connection_changed = changed
