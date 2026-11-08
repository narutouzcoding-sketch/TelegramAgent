"""Keep an answer-seeking task out of the one-way message player."""

import re


def effective_call_mode(message, mode):
    if mode != "relay" or not isinstance(message, str):
        return mode
    text = message.casefold().translate(str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'"}))
    if re.search(
        r"javob\s+kutma|faqat\s+(?:ayt|xabar|yetkaz)|just\s+(?:say|relay)|no answer needed|don't wait|только передай|ответ не нужен",
        text,
    ):
        return mode
    # A URL query is not a spoken question.
    text = re.sub(r"https?://\S+", "", text).strip()
    statement = re.search(
        r"\b(?:bilmayman|bilaman|aytaman|tushuntiraman|kelaman|kutaman|eslataman|aytamiz|bilamiz)[.!]*$",
        text,
    )
    direct = (
        text.endswith("?")
        or re.search(r"\bso'ra(?:ng|sin|b)?\b", text)
        or (
            not statement
            and re.search(
                r"\b(?:nima|nimani|nimalar|qayer\w*|qachon|qanday|nega|nechta|qancha|kim)\b", text
            )
        )
        or re.search(r"\b\w{3,}(?:ding|gan|yapti|san|siz|ay|di|ar|shi|ing)mi\b", text)
        or re.match(
            r"(?:what|where|when|who|why|how|can you|do you|did you|will you|are you|is it|что|где|когда|почему|как)\b",
            text,
        )
    )
    return "ask" if direct else mode
