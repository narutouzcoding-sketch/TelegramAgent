"""Answer explicit read-only requests without spending an AI request."""

import unicodedata


def read_reply(store, text):
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    normalized = normalized.translate(str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'"}))
    normalized = normalized.rstrip(" .?!")
    if normalized in {
        "/plans",
        "rejalarim",
        "rejalar",
        "rejalarni ko'rsat",
        "rejalaringni ko'rsat",
        "my plans",
        "show plans",
    }:
        rows = store.list_plans()
        return (
            "\n".join(f"#{r['id']} {r['title'][:160]} — {r['details'][:160]}" for r in rows[:10])
            or "Ochiq reja yo'q."
        )
    if normalized in {
        "/reminders",
        "eslatmalar",
        "eslatmalarim",
        "eslatmalarni ko'rsat",
        "my reminders",
        "show reminders",
    }:
        rows = store.list_reminders()
        return (
            "\n".join(
                f"#{r['id']} {r['title'][:160]} — {r['due_local']} ({r['mode']}, {r['state']})"
                for r in rows[:10]
            )
            or "Kutilayotgan eslatma yo'q."
        )
    if normalized in {
        "/calls",
        "qo'ng'iroqlar holati",
        "qongiroqlar holati",
        "qo'ng'iroq natijalari",
        "call results",
    }:
        rows = store.list_contact_calls()
        return (
            "\n".join(
                f"#{r['id']} {r['target'][:100]} — {r['state']}: {(r['result'] or r['message'])[:200]}"
                for r in rows[:10]
            )
            or "Qo'ng'iroq topshiriqlari yo'q."
        )
    if normalized in {
        "/contacts",
        "kontaktlar",
        "kontaktlarim",
        "kontaktlarni ko'rsat",
        "my contacts",
        "show contacts",
    }:
        rows = store.list_contacts()
        if not rows:
            return "Kontaktlar yo'q."
        reply = f"Jami {len(rows)} kontakt:\n" + "\n".join(
            f"{r['name'][:100]} — {r['reference'][:80]}" for r in rows[:20]
        )
        if len(rows) > 20:
            reply += "\nQolganlari panelda. Qidirish: /contacts ISM"
        return reply
    if normalized.startswith("/contacts "):
        query = text.strip().split(maxsplit=1)[1]
        rows = store.search_contacts(query)
        return (
            "\n".join(f"{r['name'][:100]} — {r['reference'][:80]}" for r in rows[:20])
            or "Kontakt topilmadi."
        )
    return None
