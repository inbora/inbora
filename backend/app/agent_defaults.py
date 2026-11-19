"""Default website-chat greeting, per language. Shown in the panel until the
business writes its own."""

DEFAULTS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Hi! 👋 How can we help you today?",
    },
    "he": {
        "greeting": "שלום! 👋 איך אפשר לעזור לך היום?",
    },
    "ar": {
        "greeting": "مرحبًا! 👋 كيف يمكننا مساعدتك اليوم؟",
    },
}


def default_for(language: str, field: str) -> str:
    return DEFAULTS.get(language, DEFAULTS["en"])[field]
