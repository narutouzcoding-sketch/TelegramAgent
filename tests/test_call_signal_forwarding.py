import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import TelegramClient
from telethon.network.mtprotosender import MTProtoSender
from telethon.sessions import StringSession
from telethon.tl import functions, types

from telegram_agent.call_outcomes import connection_outcome
from telegram_agent.call_signals import CallSignals, forward_exported_updates, trace_phone_rpc


def accepted(peer=77):
    return types.UpdatePhoneCall(
        types.PhoneCallAccepted(
            id=900,
            access_hash=123,
            date=datetime.now(timezone.utc),
            admin_id=42,
            participant_id=peer,
            g_b=b"PRIVATE_DH_BYTES",
            protocol=types.PhoneCallProtocol(
                min_layer=92, max_layer=92, library_versions=["13.0.0"]
            ),
        )
    )


async def test_actual_telethon_exported_sender_drops_acceptance_without_queue_and_fix_forwards():
    sender = MTProtoSender(None, loggers=defaultdict(lambda: logging.getLogger("test-sender")))
    update = types.UpdateShort(accepted(), datetime.now(timezone.utc))
    message = SimpleNamespace(obj=update)
    # This is the actual installed receiver, not a mocked approximation.
    with pytest.raises(AttributeError, match="put_nowait"):
        await sender._handle_update(message)
    queue = asyncio.Queue()
    original = AsyncMock(return_value=sender)
    client = SimpleNamespace(_updates_queue=queue, _borrow_exported_sender=original)
    forward_exported_updates(client)
    assert await client._borrow_exported_sender(5) is sender
    await sender._handle_update(message)
    assert queue.get_nowait() is update
    original.assert_awaited_once_with(5)


async def test_forwarder_is_idempotent_and_preserves_existing_queue():
    existing = asyncio.Queue()
    sender = SimpleNamespace(_updates_queue=existing)
    client = SimpleNamespace(
        _updates_queue=asyncio.Queue(), _borrow_exported_sender=AsyncMock(return_value=sender)
    )
    forward_exported_updates(client)
    wrapper = client._borrow_exported_sender
    forward_exported_updates(client)
    assert client._borrow_exported_sender is wrapper
    await client._borrow_exported_sender(3)
    assert sender._updates_queue is existing


async def test_real_telethon_type_remains_compatible_with_pytgcalls_detection():
    from pytgcalls.mtproto.bridged_client import BridgedClient

    client = TelegramClient(StringSession(), 1, "test-only")
    forward_exported_updates(client)
    assert BridgedClient.package_name(client) == "telethon"
    await client.disconnect()


async def test_actual_pytgcalls_adapter_delivers_accepted_update_to_handshake_future():
    from pytgcalls.methods.internal.handle_mtproto_updates import HandleMTProtoUpdates
    from pytgcalls.mtproto.telethon_client import TelethonClient

    class FakeTelegram:
        _no_updates = False

        def on(self, event):
            def register(callback):
                self.callback = callback
                return callback

            return register

    telegram = FakeTelegram()
    bridge = TelethonClient(3600, telegram)
    future = asyncio.get_running_loop().create_future()
    calls = SimpleNamespace(
        _p2p_configs={77: SimpleNamespace(wait_data=future, outgoing=True)}, _wait_connect={}
    )

    async def receive(update):
        await HandleMTProtoUpdates._handle_mtproto_updates(calls, update)

    bridge.add_handler(receive)
    await telegram.callback(accepted())
    assert future.done() and future.result().chat_id == 77


async def test_call_trace_tracks_acceptance_without_crypto_or_foreign_call_data():
    trace = CallSignals(42)
    metrics = {"connected": False}
    trace.begin(77, metrics, 9)
    await trace.observe(accepted(peer=88))
    assert not metrics["telegram_accepted"]
    await trace.observe(accepted())
    assert metrics["telegram_accepted"] and metrics["stage"] == "accepted_waiting_media"
    await trace.observe(types.UpdatePhoneCallSignalingData(900, b"PRIVATE_SIGNAL"))
    assert metrics["signaling_received"] == 1
    trace.exported(5)
    data = json.dumps(trace.snapshot())
    assert "PRIVATE" not in data and "access_hash" not in data and "g_b" not in data
    trace.end()
    assert trace.peer_id is None and metrics["ended"]


async def test_rpc_trace_observes_dc_reroute_without_reissuing_requests():
    trace = CallSignals(42)
    trace.begin(77, {}, 9)
    original = AsyncMock(return_value="same result")
    bridge = SimpleNamespace(
        _invoke=original, _app=SimpleNamespace(session=SimpleNamespace(dc_id=2))
    )
    calls = SimpleNamespace(_app=SimpleNamespace(_bind_client=bridge))
    trace_phone_rpc(calls, trace)
    request = functions.phone.RequestCallRequest(
        user_id=types.InputUser(77, 123),
        random_id=1,
        g_a_hash=b"PRIVATE_KEY",
        protocol=types.PhoneCallProtocol(92, 92, ["13.0.0"]),
    )
    assert await bridge._invoke(request, dc_id=5) == "same result"
    original.assert_awaited_once_with(request, 5, None, None)
    assert trace.events[0]["dc"] == 5
    assert "PRIVATE" not in json.dumps(trace.snapshot())


def test_accepted_but_unconnected_is_media_failure_not_unanswered():
    state, report = connection_outcome("TimedOutAnswer", 60, accepted=True)
    assert state == "connection_failed" and "qabul qilinganini" in report
    assert "ovoz kanali ochilmadi" in report
