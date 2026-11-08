"""A recording or greeting is not evidence that the owner's question was answered."""

import json
import re
import unicodedata


def normalized(text):
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'"}))
    return " ".join(re.findall(r"[\w']+", text)).strip(" '")


def greeting_or_clarification(text):
    value = normalized(text)
    if value in {
        "alo",
        "allo",
        "salom",
        "hello",
        "hi",
        "assalomu alaykum",
        "va alaykum assalom",
        "xayrli kech",
        "good evening",
        "kim",
        "kimsiz",
        "kim bu",
        "bu kim",
        "nima",
        "what",
        "pardon",
        "repeat",
        "ha eshitaman",
        "алло",
        "кто это",
    }:
        return True
    greeting_remainder = value
    for greeting in (
        "assalomu alaykum",
        "va alaykum assalom",
        "xayrli kech",
        "good evening",
        "hello",
        "salom",
    ):
        greeting_remainder = greeting_remainder.replace(greeting, " ").strip()
    if not greeting_remainder:
        return True
    patterns = (
        r"could you repeat",
        r"repeat the question",
        r"say that again",
        r"who is this",
        r"cannot hear",
        r"can't hear",
        r"eshitmayap\w*",
        r"eshitolmayap\w*",
        r"tushunmadim",
        r"takrorla\w*",
        r"qaytaring",
        r"qayta ayt\w*",
        r"kim gapiryap\w*",
        r"повторите",
        r"не слышу",
    )
    remainder = greeting_remainder
    matched = False
    for pattern in patterns:
        remainder, count = re.subn(pattern, " ", remainder)
        matched = matched or bool(count)
    fillers = {
        "i",
        "you",
        "me",
        "the",
        "a",
        "this",
        "that",
        "question",
        "please",
        "again",
        "it",
        "can",
        "iltimos",
        "yana",
        "savolni",
        "savol",
        "menga",
        "sizni",
        "я",
        "вас",
        "вопрос",
        "пожалуйста",
    }
    return matched and all(w in fillers for w in remainder.split())


def refusal(text):
    value = normalized(text)
    return any(
        term in value
        for term in (
            "javob bermayman",
            "aytmayman",
            "gaplashishni istamayman",
            "gaplashmayman",
            "qo'ng'iroq qilmang",
            "boshqa telefon qilmang",
            "stop calling",
            "don't call",
            "do not call",
            "leave me alone",
            "i don't want to answer",
            "i do not want to answer",
            "не звоните",
            "не хочу отвечать",
        )
    )


def echo_of_question(text, question):
    a, b = normalized(text), normalized(question)
    if len(b.split()) < 3:
        return False
    return a == b or (len(a.split()) >= 4 and a in b)


def parse_verdict(raw, utterance):
    value = json.loads(
        raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    if not isinstance(value, dict) or value.get("status") not in {
        "answered",
        "partial",
        "clarification",
        "unrelated",
        "unclear",
        "declined",
    }:
        raise ValueError("Missing answer verdict")
    status = value["status"]
    quote = value.get("answer", "")
    if status in {"answered", "partial", "declined"}:
        if (
            not isinstance(quote, str)
            or not normalized(quote)
            or not re.search(
                r"(?<!\w)" + re.escape(normalized(quote)) + r"(?!\w)", normalized(utterance)
            )
        ):
            raise ValueError("Answer must be an exact recipient quote")
        if greeting_or_clarification(quote):
            raise ValueError("Greeting is not an answer")
    else:
        quote = ""
    followup = value.get("reply", "")
    return status, quote[:2000], followup[:500] if isinstance(followup, str) else ""
