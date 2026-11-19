"""Everything about one business the agent needs: name, settings, knowledge."""
from dataclasses import dataclass, field

from .. import db
from ..agent_defaults import default_for

LANG_NAMES = {"en": "English", "he": "Hebrew", "ar": "Arabic"}


@dataclass
class Article:
    title: str
    body: str


@dataclass
class TenantContext:
    tenant_id: str
    business_name: str
    default_language: str = "en"
    instructions: str = ""
    tone: str = "friendly"
    greeting: str | None = None
    collect_contact: str = "email"       # what to ask a website visitor for: email|phone|either|none
    articles: list[Article] = field(default_factory=list)
    kb_char_limit: int = 20000

    @property
    def language_name(self) -> str:
        return LANG_NAMES.get(self.default_language, "English")


def load(tenant_id: str) -> TenantContext:
    tenant = db.select_one("tenants", {"select": "name,default_language", "id": f"eq.{tenant_id}"})
    if tenant is None:
        raise LookupError(f"tenant {tenant_id} not found")
    settings = db.select_one("agent_settings", {"select": "*", "tenant_id": f"eq.{tenant_id}"}) or {}
    sub = db.select_one("subscriptions", {
        "select": "limits", "tenant_id": f"eq.{tenant_id}", "status": "eq.active",
    })
    rows = db.select("kb_articles", {
        "select": "title,body",
        "tenant_id": f"eq.{tenant_id}",
        "enabled": "eq.true",
        "order": "sort_order.asc,created_at.asc",
    })
    limit = int(((sub or {}).get("limits") or {}).get("kb_char_limit") or 20000)
    lang = settings.get("default_language") or tenant.get("default_language") or "en"
    return TenantContext(
        tenant_id=tenant_id,
        business_name=tenant["name"],
        default_language=lang,
        instructions=(settings.get("instructions") or "").strip(),
        tone=(settings.get("tone") or "friendly").strip(),
        greeting=(settings.get("greeting") or "").strip() or default_for(lang, "greeting"),
        collect_contact=settings.get("collect_contact") or "email",
        articles=[Article(r["title"], r["body"] or "") for r in rows],
        kb_char_limit=limit,
    )
