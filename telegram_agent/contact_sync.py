"""Import only contacts; never send messages or fetch chat history."""

import asyncio

from telethon import functions

from .config import ROOT


async def telegram_contacts(client, own_id):
    result = await client(functions.contacts.GetContactsRequest(hash=0))
    rows = []
    for user in result.users:
        if user.id == own_id or user.bot or user.deleted:
            continue
        reference = (
            "@" + user.username
            if user.username
            else "+" + user.phone
            if user.phone
            else f"id:{user.id}"
        )
        rows.append(
            {
                "name": " ".join(filter(None, (user.first_name, user.last_name))) or reference,
                "reference": reference,
                "telegram_id": user.id,
            }
        )
    return rows


def exported_contacts(value):
    if not isinstance(value, (dict, list)):
        raise ValueError("Telegram kontakt JSON faylini tanlang.")
    rows = value.get("contacts", value) if isinstance(value, dict) else value
    if isinstance(rows, dict):
        rows = rows.get("list", [])
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError("Kontaktlar ro'yxati noto'g'ri yoki 20000 dan ortiq.")
    contacts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "").strip().lstrip("@")
        phone = "".join(
            c for c in str(row.get("phone_number") or row.get("phone") or "") if c.isdigit()
        )
        reference = "@" + username if username else "+" + phone if phone else row.get("reference")
        if reference:
            contacts.append(
                {
                    "name": row.get("name")
                    or " ".join(filter(None, (row.get("first_name"), row.get("last_name"))))
                    or reference,
                    "reference": reference,
                }
            )
    return contacts


async def sync_linked_contacts(settings, store, root=ROOT):
    from telethon import TelegramClient

    from .telegram_health import ensure_telegram_account

    path = root / "data" / "owner-contacts"
    if not path.with_suffix(".session").exists():
        return {"imported": 0, "linked": False}
    client = TelegramClient(
        str(path),
        settings.api_id,
        settings.api_hash,
        request_retries=0,
        flood_sleep_threshold=0,
        connection_retries=1,
        timeout=10,
    )
    try:
        async with asyncio.timeout(30):
            await client.connect()
            if not await client.is_user_authorized():
                return {"imported": 0, "linked": False}
            me = await ensure_telegram_account(client, settings.timezone)
            result = store.import_contacts(
                await telegram_contacts(client, me.id),
                "owner-telegram" if me.id == settings.owner_id else "linked-telegram",
            )
            return {**result, "linked": True}
    finally:
        await client.disconnect()
