"""Validate setup inputs locally without displaying credentials."""

import re


def telegram_credentials(api_id, api_hash):
    identifier = str(api_id).strip()
    if not identifier.isascii() or not identifier.isdecimal():
        raise ValueError(
            "Telegram API ID maydoniga faqat my.telegram.org dagi api_id sonini kiriting."
        )
    identifier = int(identifier)
    if not 0 < identifier <= 2_147_483_647:
        raise ValueError(
            "Telegram API ID noto'g'ri. my.telegram.org/apps dagi api_id ni tekshiring."
        )
    secret = str(api_hash).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", secret):
        raise ValueError(
            "Telegram API hash 32 ta 0-9/a-f belgidan iborat bo'lishi kerak. "
            "my.telegram.org/apps dagi api_hash qiymatini to'liq nusxalang; "
            "yorliq, qo'shtirnoq yoki OpenAI kalitini qo'shmang."
        )
    return identifier, secret


def international_phone(value):
    number = re.sub(r"[\s()\-]", "", value)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
        raise ValueError(
            "Telefon raqamini + va mamlakat kodi bilan kiriting. "
            "Masalan, O'zbekiston raqami: +998901234567. "
            "Faqat mahalliy 9 xonali raqam yetarli emas."
        )
    return number


def prompt_phone():
    while True:
        try:
            return international_phone(
                input("Yordamchi akkaunt telefon raqami (+mamlakat_kodi...): ").strip()
            )
        except ValueError as exc:
            print(exc)
