"""Consistent matching for Telegram names, formatted phones and Uzbek apostrophes."""

import re
import unicodedata


def normalized(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join(
        re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c)))
    )


def contact_matches(contact, query):
    text = normalized(contact.get("name", "") + " " + contact.get("reference", ""))
    terms = normalized(query).split()
    digits = "".join(re.findall(r"\d", query))
    if (
        digits
        and not re.search(r"[^\W\d_]", query)
        and digits in "".join(re.findall(r"\d", contact.get("reference", "")))
    ):
        return True
    return bool(terms) and all(
        (
            any(part.startswith(word) for part in text.split())
            if word.isdecimal()
            else (
                word in text
                or (len(word) > 5 and re.sub(r"(?:ning|dagi|dan|ga|ni)$", "", word) in text)
            )
        )
        for word in terms
    )
