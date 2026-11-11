"""Deliver an owner-requested message once and retain the exact Telegram reply link."""

import asyncio

from telethon.errors import RPCError
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import UpdateMessageID, UpdateShortSentMessage

from .telegram_policy import TelegramPaused


def message_body(owner_name, message, language):
    introductions = {
        "uz": f"Assalomu alaykum. Men {owner_name}ning AI yordamchisiman. Uning xabari quyida.",
        "en": f"Hello. I am {owner_name}'s AI assistant. Here is their message.",
        "ru": f"Здравствуйте. Я ИИ-помощник {owner_name}. Ниже сообщение от владельца.",
    }
    instructions = {
        "uz": "Yozma javobingizni ushbu xabarga Reply qilib yuboring.",
        "en": "Please reply directly to this message with your answer.",
        "ru": "Пожалуйста, ответьте на это сообщение через Reply.",
    }
    return f"{introductions[language]}\n\n{message}\n\n{instructions[language]}"


def sent_message_id(response, random_id):
    if isinstance(response, UpdateShortSentMessage):
        return response.id
    for update in getattr(response, "updates", ()):
        if isinstance(update, UpdateMessageID) and update.random_id == random_id:
            return update.id
    return None


async def send_contact_message(app, job, user, reason=""):
    report = f"Vazifa #{job['id']}: {job['target']}. "
    if reason:
        report += reason.rstrip(".") + ". "
    try:
        if user.id not in app.settings.allowed_call_user_ids:
            raise ValueError("Kontakt ruxsati olib tashlangan.")
        if job.get("recipient_user_id") and job["recipient_user_id"] != user.id:
            raise ValueError("Kontaktning Telegram akkaunti o'zgargan.")
        body = message_body(app.owner_name[:100], job["message"], job.get("language", "uz"))
        if job.get("mode") == "voice":
            from .voice_library import asset_path

            path, _ = asset_path(app.store, job["audio_id"])
        else:
            peer = await app.policy.action(lambda: app.telegram.get_input_entity(user))
        random_id = app.store.begin_contact_text(job["id"], user.id, body)
        job["text_random_id"] = random_id
        if job.get("mode") == "voice":
            response = await app.policy.send(
                lambda: app.telegram.send_file(user, str(path), voice_note=True, caption=body)
            )
            message_id = response.id
        else:
            response = await app.policy.send(
                lambda: app.telegram(SendMessageRequest(peer, body, random_id=random_id))
            )
            message_id = sent_message_id(response, random_id)
        if not message_id:
            report += "Xabar yuborish natijasi tasdiqlanmadi. Holatni Telegram chatida tekshiring."
            app.store.finish_contact_text(job["id"], app.settings.owner_id, "interrupted", report)
            return report
    except asyncio.CancelledError:
        app.store.finish_contact_text(
            job["id"],
            app.settings.owner_id,
            "interrupted",
            report + "Xabar yuborish uzilgan; yetkazilgani tasdiqlanmagan.",
        )
        raise
    except Exception as exc:
        # An interrupted network send may already have reached Telegram.
        uncertain = bool(job.get("text_random_id")) and not isinstance(exc, (RPCError, ValueError))
        report += (
            "Xabar yuborish natijasi noma'lum. Telegram chatida tekshiring."
            if uncertain
            else "Telegram xabari yuborilmadi."
        )
        if isinstance(exc, TelegramPaused):
            report += " Sabab: " + str(exc)[:500]
        else:
            report += f" Sabab: {type(exc).__name__}."
        app.store.finish_contact_text(
            job["id"],
            app.settings.owner_id,
            "interrupted" if uncertain else "text_failed",
            report,
        )
        return report
    report += "Telegram xabari yuborildi. O'qilgani va javob kelgani hali tasdiqlanmagan."
    app.store.finish_contact_text(job["id"], app.settings.owner_id, "text_sent", report, message_id)
    return report
