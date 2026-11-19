"""Default greeting and hand-off message, per language. Shown in the panel
until the business writes its own, and used by the agent and the website chat."""

DEFAULTS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Hi! 👋 How can we help you today?",
        "escalation_message": "Thanks for your patience! I've passed your request to our team, "
                              "and they'll get back to you as soon as possible.",
    },
    "he": {
        "greeting": "שלום! 👋 איך אפשר לעזור לך היום?",
        "escalation_message": "תודה על הסבלנות! העברתי את הפנייה שלך לצוות שלנו, "
                              "והם יחזרו אליך בהקדם האפשרי.",
    },
    "ar": {
        "greeting": "مرحبًا! 👋 كيف يمكننا مساعدتك اليوم؟",
        "escalation_message": "شكرًا على صبرك! لقد حوّلت طلبك إلى فريقنا، "
                              "وسيتواصلون معك في أقرب وقت ممكن.",
    },
}


def default_for(language: str, field: str) -> str:
    return DEFAULTS.get(language, DEFAULTS["en"])[field]
