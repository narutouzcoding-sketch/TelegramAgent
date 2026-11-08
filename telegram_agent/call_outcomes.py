"""Connection outcomes are different from a connected caller's missing answer."""


def connection_outcome(error, timeout=None, connected=False, accepted=False):
    if connected:
        return None
    name = type(error).__name__ if not isinstance(error, str) else error
    if accepted and name not in {
        "CallBusy",
        "CallDeclined",
        "CallDiscarded",
        "UserPrivacyRestrictedError",
    }:
        return (
            "connection_failed",
            "Telegram qo'ng'iroq qabul qilinganini bildirdi, ammo ovoz kanali ochilmadi. Savol eshittirilmadi. Suhbat yozuvi yaratilmagan. Avtomatik qayta terilmadi.",
        )
    wait = f" ({timeout} soniyagacha kutildi)" if timeout else ""
    explanations = {
        "TimedOutAnswer": (
            "unanswered",
            "Telegram qo'ng'iroq qabul qilingani yoki ovoz ulanishini tasdiqlamadi" + wait + ".",
        ),
        "CallBusy": ("busy", "Telegram kontakt bandligini bildirdi."),
        "CallDeclined": ("rejected", "Telegram qo'ng'iroq rad etilganini bildirdi."),
        "CallDiscarded": ("unanswered", "Qo'ng'iroq ulanish tasdiqlanmasidan tugadi."),
        "UserPrivacyRestrictedError": (
            "privacy_blocked",
            "Kontaktning Telegram maxfiylik sozlamasi qo'ng'iroqqa ruxsat bermadi.",
        ),
    }
    value = explanations.get(name)
    if value is None:
        return None
    state, reason = value
    return (
        state,
        reason + " Savol eshittirilmadi. Suhbat yozuvi yaratilmagan. Avtomatik qayta terilmadi.",
    )
