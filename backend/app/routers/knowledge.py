"""Knowledge articles: what the agent knows about the business.

The plan limits the total size (in characters) of the articles that are
switched on. Switched-off articles are drafts and don't count."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, jobs, site_import
from ..tenancy import current_tenant_id
from ..templates_kb import TEMPLATE_KEYS, TEMPLATES

router = APIRouter(prefix="/knowledge")

MAX_TITLE = 200
MAX_BODY = 100_000
_FIELDS = "id,title,body,enabled,char_count,sort_order,created_at,updated_at"


def _limit(tenant_id: str) -> int:
    sub = db.select_one("subscriptions", {
        "select": "limits", "tenant_id": f"eq.{tenant_id}", "status": "eq.active",
    })
    return int(((sub or {}).get("limits") or {}).get("kb_char_limit") or 0)


def _articles(tenant_id: str) -> list[dict]:
    return db.select("kb_articles", {
        "select": _FIELDS, "tenant_id": f"eq.{tenant_id}", "order": "sort_order.asc,created_at.asc",
    })


def _used(articles: list[dict], excluding: str | None = None) -> int:
    return sum(a["char_count"] for a in articles if a["enabled"] and a["id"] != excluding)


def _check_room(tenant_id: str, size: int, excluding: str | None = None) -> None:
    """Refuse when switching this article on would go over the plan's limit."""
    limit = _limit(tenant_id)
    used = _used(_articles(tenant_id), excluding)
    if used + size > limit:
        raise HTTPException(422, {
            "code": "kb_limit",
            "message": "This would go over your plan's knowledge limit.",
            "limit": limit, "used": used, "needed": size,
        })


def _size(title: str, body: str) -> int:
    return len(title) + len(body)


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    body: str = Field(default="", max_length=MAX_BODY)
    enabled: bool = True


class ArticlePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    enabled: bool | None = None


class TemplatesIn(BaseModel):
    keys: list[Literal["shipping", "returns", "payment", "contact", "hours"]] = Field(min_length=1)
    language: Literal["en", "he", "ar"] = "en"


@router.get("")
def list_articles(tenant_id: str = Depends(current_tenant_id)):
    arts = _articles(tenant_id)
    return {"articles": arts, "used": _used(arts), "limit": _limit(tenant_id)}


@router.post("", status_code=201)
def create_article(body: ArticleIn, tenant_id: str = Depends(current_tenant_id)):
    title, text = body.title.strip(), body.body.strip()
    if not title:
        raise HTTPException(422, {"code": "title_required", "message": "The title is required."})
    if body.enabled:
        _check_room(tenant_id, _size(title, text))
    last = db.select_one("kb_articles", {
        "select": "sort_order", "tenant_id": f"eq.{tenant_id}", "order": "sort_order.desc",
    })
    row = db.insert("kb_articles", {
        "tenant_id": tenant_id, "title": title, "body": text, "enabled": body.enabled,
        "sort_order": (last["sort_order"] + 1) if last else 0,
    })[0]
    return {k: row[k] for k in _FIELDS.split(",")}


@router.put("/{article_id}")
def update_article(article_id: str, patch: ArticlePatch, tenant_id: str = Depends(current_tenant_id)):
    current = db.select_one("kb_articles", {
        "select": _FIELDS, "id": f"eq.{article_id}", "tenant_id": f"eq.{tenant_id}",
    })
    if current is None:
        raise HTTPException(404, "Article not found")
    title = patch.title.strip() if patch.title is not None else current["title"]
    text = patch.body.strip() if patch.body is not None else current["body"]
    enabled = patch.enabled if patch.enabled is not None else current["enabled"]
    if not title:
        raise HTTPException(422, {"code": "title_required", "message": "The title is required."})
    # Only check when the article will be on and gets bigger (or is being switched on):
    # shrinking or switching off is always allowed, even when already over the limit.
    new_size = _size(title, text)
    if enabled and (not current["enabled"] or new_size > current["char_count"]):
        _check_room(tenant_id, new_size, excluding=article_id)
    row = db.update("kb_articles", {"id": f"eq.{article_id}", "tenant_id": f"eq.{tenant_id}"},
                    {"title": title, "body": text, "enabled": enabled})[0]
    return {k: row[k] for k in _FIELDS.split(",")}


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: str, tenant_id: str = Depends(current_tenant_id)):
    db.delete("kb_articles", {"id": f"eq.{article_id}", "tenant_id": f"eq.{tenant_id}"})


@router.get("/templates")
def list_templates():
    return {"keys": TEMPLATE_KEYS,
            "templates": {lang: {k: {"title": t[0], "body": t[1]} for k, t in items.items()}
                          for lang, items in TEMPLATES.items()}}


@router.post("/templates", status_code=201)
def add_templates(body: TemplatesIn, tenant_id: str = Depends(current_tenant_id)):
    """Adds the chosen templates switched off: the [brackets] must be filled in
    before the agent should use them."""
    last = db.select_one("kb_articles", {
        "select": "sort_order", "tenant_id": f"eq.{tenant_id}", "order": "sort_order.desc",
    })
    start = (last["sort_order"] + 1) if last else 0
    rows = [{"tenant_id": tenant_id, "title": TEMPLATES[body.language][k][0],
             "body": TEMPLATES[body.language][k][1], "enabled": False, "sort_order": start + i}
            for i, k in enumerate(dict.fromkeys(body.keys))]
    created = db.insert("kb_articles", rows)
    return {"articles": [{k: r[k] for k in _FIELDS.split(",")} for r in created]}


# ── Import from the business's website

_IMPORT_FIELDS = "id,url,language,status,pages_done,pages_total,pages_read,suggestions,error,created_at"


class ImportIn(BaseModel):
    url: str = Field(min_length=3, max_length=300)
    language: Literal["en", "he", "ar"] = "en"


class ImportedArticle(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    body: str = Field(min_length=1, max_length=MAX_BODY)


class ApplyIn(BaseModel):
    articles: list[ImportedArticle] = Field(min_length=1, max_length=20)


def _import_view(row: dict, tenant_id: str) -> dict:
    titles = {a["title"].strip().lower() for a in _articles(tenant_id)}
    return {**row, "suggestions": [{**s, "exists": s["title"].strip().lower() in titles}
                                   for s in (row.get("suggestions") or [])]}


@router.get("/import")
def get_import(tenant_id: str = Depends(current_tenant_id)):
    """The latest import still running or waiting for review, and the saved website."""
    row = db.select_one("site_imports", {"select": _IMPORT_FIELDS, "tenant_id": f"eq.{tenant_id}",
                                         "status": "in.(queued,reading,writing,ready,failed)",
                                         "order": "created_at.desc"})
    tenant = db.select_one("tenants", {"select": "website", "id": f"eq.{tenant_id}"}) or {}
    return {"import": _import_view(row, tenant_id) if row else None, "website": tenant.get("website") or ""}


@router.post("/import", status_code=201)
def start_import(body: ImportIn, tenant_id: str = Depends(current_tenant_id)):
    url = site_import.normalize(body.url)
    if not url:
        raise HTTPException(422, {"code": "bad_url"})
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    recent = db.select("site_imports", {"select": "id", "tenant_id": f"eq.{tenant_id}", "created_at": f"gte.{since}"})
    if len(recent) >= site_import.DAILY_LIMIT:
        raise HTTPException(429, {"code": "import_limit", "limit": site_import.DAILY_LIMIT})
    # One at a time: an earlier import that wasn't finished is closed.
    db.update("site_imports", {"tenant_id": f"eq.{tenant_id}", "status": "in.(queued,reading,writing,ready,failed)"},
              {"status": "dismissed"})
    db.update("tenants", {"id": f"eq.{tenant_id}"}, {"website": url})
    row = db.insert("site_imports", {"tenant_id": tenant_id, "url": url, "language": body.language})[0]
    jobs.enqueue("site_import", tenant_id, {"import_id": row["id"]})
    return {"import": {k: row[k] for k in _IMPORT_FIELDS.split(",")}}


@router.post("/import/{import_id}/apply", status_code=201)
def apply_import(import_id: str, body: ApplyIn, tenant_id: str = Depends(current_tenant_id)):
    """Adds the articles the business kept (switched on)."""
    row = db.select_one("site_imports", {"select": "id,status", "id": f"eq.{import_id}", "tenant_id": f"eq.{tenant_id}"})
    if row is None or row["status"] != "ready":
        raise HTTPException(404, "Import not found")
    arts = [(a.title.strip(), a.body.strip()) for a in body.articles]
    if any(not t or not b for t, b in arts):
        raise HTTPException(422, {"code": "title_required", "message": "Each article needs a title and content."})
    _check_room(tenant_id, sum(_size(t, b) for t, b in arts))
    last = db.select_one("kb_articles", {"select": "sort_order", "tenant_id": f"eq.{tenant_id}", "order": "sort_order.desc"})
    start = (last["sort_order"] + 1) if last else 0
    created = db.insert("kb_articles", [{"tenant_id": tenant_id, "title": t, "body": b, "enabled": True,
                                         "sort_order": start + i} for i, (t, b) in enumerate(arts)])
    db.update("site_imports", {"id": f"eq.{import_id}"}, {"status": "done"})
    return {"articles": [{k: r[k] for k in _FIELDS.split(",")} for r in created]}


@router.delete("/import/{import_id}", status_code=204)
def dismiss_import(import_id: str, tenant_id: str = Depends(current_tenant_id)):
    db.update("site_imports", {"id": f"eq.{import_id}", "tenant_id": f"eq.{tenant_id}",
                               "status": "in.(queued,reading,writing,ready,failed)"}, {"status": "dismissed"})
