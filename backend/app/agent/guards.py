"""Checks on the model's reply before it reaches a customer (ported from Grinta)."""
import re

FALLBACK = {
    "en": "Sorry, we hit a temporary technical problem. Could you try again or rephrase your message?",
    "he": "מצטערים, נתקלנו בבעיה טכנית רגעית. אפשר לנסות שוב או לנסח מחדש את הפנייה?",
    "ar": "عذرًا، واجهنا مشكلة تقنية مؤقتة. هل يمكنك المحاولة مرة أخرى أو إعادة صياغة رسالتك؟",
}


def fallback(lang: str) -> str:
    return FALLBACK.get(lang, FALLBACK["en"])


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought a model may leak into its reply. Only acts when
    the text carries a reasoning label (THOUGHT/THINK/REASONING), so an ordinary
    reply is never touched.
    - If a final-answer label (RESPONSE:/ANSWER:/REPLY:) follows, keep only what
      comes after the last such label.
    - Else, if it opens with a reasoning block ending at a blank line, drop it."""
    if not text:
        return text
    t = text.strip()
    if not re.search(r"(?i)\b(?:THOUGHT|THINK|REASONING)\b[ \t]*:?", t):
        return t
    answers = list(re.finditer(r"(?i)\b(?:RESPONSE|ANSWER|FINAL ANSWER|REPLY)\b[ \t]*:[ \t]*", t))
    if answers:
        return t[answers[-1].end():].strip()
    m = re.match(r"(?is)^\s*(?:THOUGHT|THINK|REASONING)\b[ \t]*:?", t)
    if m:
        blocks = re.split(r"\n[ \t]*\n", t[m.end():], maxsplit=1)
        if len(blocks) == 2 and blocks[1].strip():
            return blocks[1].strip()
    return t


def looks_like_raw_output(text: str) -> bool:
    """True if the reply is a raw tool/JSON/HTML blob rather than a sentence.
    Kept tight so ordinary replies are never caught."""
    if not text:
        return False
    t = text.strip()
    if re.search(r"</?(?:body|html|head|div|span|table|td|tr|p|br|style)\b", t, re.IGNORECASE):
        return True
    if t.startswith("<") and ">" in t:
        return True
    if re.search(r"\{\s*[\"'](?:error|success|escalated|saved|found|message)[\"']\s*:", t):
        return True
    if t.startswith(("{", "[")) and re.search(r"[\"'](?:error|success|escalated|saved|found)[\"']", t):
        return True
    return False


def plausible_name(name: str | None) -> str:
    """The name only if it could be a personal name — not a phone number or email."""
    name = (name or "").strip()
    if not name or "@" in name:
        return ""
    if re.sub(r"[\s+\-()]", "", name).isdigit():
        return ""
    return name[:80]
