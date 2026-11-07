"""Bind the controlling account without confusing its ID with a Telegram API ID."""

import asyncio
import secrets

from telethon import events
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.types import User

PLACEHOLDERS = {
    "@asosiy_akkauntingiz",
    "@sizning_asosiy_akkauntingiz",
    "@sizning_asosiy_username",
    "@your_username",
    "@username",
    "@",
}


def valid_owner(user, own_id):
    return isinstance(user, User) and not user.bot and not user.deleted and user.id != own_id


async def configured_owner(client, own_id, username="", owner_id=""):
    username = (username or "").strip()
    # An explicit username takes priority over a stale or mistyped numeric ID.
    if username and username.casefold() not in PLACEHOLDERS:
        try:
            user = await client.get_entity(username)
            if valid_owner(user, own_id):
                return user
        except (ValueError, UsernameInvalidError, UsernameNotOccupiedError):
            pass
    identifier = str(owner_id or "").strip()
    if identifier.isascii() and identifier.isdecimal():
        try:
            await client.get_dialogs(limit=200)
            user = await client.get_entity(int(identifier))
            if valid_owner(user, own_id):
                return user
        except ValueError:
            pass
    return None


async def pair_owner(client, own_id, timeout=300):
    code = secrets.token_hex(8)
    command = "/pair " + code
    future = asyncio.get_running_loop().create_future()

    async def receive(event):
        if future.done() or not event.is_private or event.out or event.sender_id == own_id:
            return
        if not secrets.compare_digest(
            event.raw_text.strip().encode("utf-8"), command.encode("ascii")
        ):
            return
        user = await event.get_sender()
        if valid_owner(user, own_id) and not future.done():
            future.set_result(user)

    client.add_event_handler(receive, events.NewMessage(incoming=True))
    print("OWNER — sizning avvaldan ishlatadigan asosiy shaxsiy Telegram akkauntingiz.")
    print("Asosiy akkauntingizdan YANGI YORDAMCHI akkauntiga mana bu xabarni yuboring:")
    print(command, flush=True)
    print("Kod 5 daqiqa amal qiladi. Shu chatga yoki boshqa odamlarga yubormang.", flush=True)
    try:
        return await asyncio.wait_for(future, timeout)
    except TimeoutError:
        raise ValueError(
            "Asosiy akkauntdan ulash xabari kelmadi. login.ps1 ni qayta ochib, yangi /pair "
            "buyrug'ini asosiy akkauntingizdan yordamchiga yuboring. Telegram sessiya saqlangan."
        ) from None
    finally:
        client.remove_event_handler(receive)
