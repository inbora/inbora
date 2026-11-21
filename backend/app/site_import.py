"""Knowledge from the business's website.

The worker reads the site's useful pages (shipping, returns, FAQ, contact…),
then Gemini writes knowledge articles using only what the pages say. The
articles are suggestions: the business reviews them before anything is added."""
import heapq
import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from google.genai import types

from . import db, errors, usage
from .agent import gemini

MAX_PAGES = 30            # pages fetched per import
MAX_BYTES = 2_000_000     # per page
PAGE_CHARS = 6_000        # text kept per page
TOTAL_CHARS = 120_000     # text sent to the AI
MAX_SECONDS = 150         # reading time per import
MAX_ARTICLES = 12
DAILY_LIMIT = 5           # imports per business per 24 hours
USER_AGENT = "InboraBot/1.0 (+https://inbora.ai)"
LANGS = {"en": "English", "he": "Hebrew", "ar": "Arabic"}
ALLOW_PRIVATE = False     # tests only: lets the importer read a local test site

# Words in a page's address or link text that point to what customers ask about.
_USEFUL = [
    "ship", "deliver", "return", "refund", "exchange", "polic", "faq", "question", "help", "support",
    "contact", "about", "story", "terms", "condition", "payment", "size", "warranty", "guarantee",
    "hours", "location", "store", "branch", "cancel",
    "משלוח", "החזר", "החלפ", "ביטול", "מדיניות", "שאלות", "תקנון", "צור קשר", "צרו קשר", "אודות",
    "תשלום", "מידות", "אחריות", "שעות", "סניפ",
    "شحن", "توصيل", "إرجاع", "ارجاع", "استبدال", "استرجاع", "سياس", "أسئلة", "اسئلة", "اتصل", "تواصل",
    "من نحن", "الدفع", "مقاس", "ضمان", "شروط", "فروع",
]
# Shopify keeps these at fixed addresses.
_KNOWN_PATHS = ["/policies/shipping-policy", "/policies/refund-policy", "/policies/terms-of-service",
                "/pages/faq", "/pages/contact", "/pages/about", "/pages/about-us"]
# Products, carts, accounts, blogs and files are not knowledge.
_SKIP = re.compile(r"/(products?|collections|product-category|shop|cart|checkout|account|login|register|search|"
                   r"blogs?|news|tag|tags|cdn|wp-admin|wp-json|feed)(/|$)|\.(jpe?g|png|gif|webp|svg|pdf|zip|"
                   r"css|js|xml|json|mp4|mp3|ico|woff2?)$", re.I)


class SiteError(Exception):
    """code: unreachable | empty | failed"""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ── Addresses

def normalize(url: str) -> str | None:
    """'grinta.co.il' → 'https://grinta.co.il'. None when it isn't a website address."""
    url = (url or "").strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme.lower() not in ("http", "https") or "." not in host or p.username or p.password:
        return None
    if p.port not in (None, 80, 443) and not ALLOW_PRIVATE:
        return None
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def _public(host: str) -> bool:
    """Only public internet addresses: never the server's own network."""
    if ALLOW_PRIVATE:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return False
    return bool(infos)


def _same_site(a: str, b: str) -> bool:
    strip = lambda h: (h or "").lower().removeprefix("www.")
    return strip(urlparse(a).hostname) == strip(urlparse(b).hostname)


def _get(client: httpx.Client, url: str) -> tuple[str, str] | None:
    """(final address, html) — follows redirects itself so every hop is checked."""
    for _ in range(5):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname or not _public(p.hostname):
            return None
        try:
            with client.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                ctype = r.headers.get("content-type", "")
                if r.status_code != 200 or not any(t in ctype for t in ("html", "xml", "text/plain")):
                    return None
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        break
                return str(r.url), data.decode(r.charset_encoding or "utf-8", errors="replace")
        except httpx.HTTPError:
            return None
    return None


# ── Reading a page

class _Page(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "aside", "iframe",
            "template", "select", "button", "head"}
    BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
              "table", "dt", "dd", "details", "summary"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self._skip = 0
        self._in_title = False
        self._link: list | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCKS:
            self.out.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._link = [href, ""]
                self.links.append(self._link)   # type: ignore[arg-type]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCKS:
            self.out.append("\n")
        if tag == "a":
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._link is not None:
            self._link[1] += data
        if not self._skip:
            self.out.append(data)

    def text(self) -> str:
        t = "".join(self.out).replace("\xa0", " ")
        t = re.sub(r"[ \t]+", " ", t)
        lines = [ln.strip() for ln in t.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _score(url: str, text: str = "") -> int:
    hay = (unquote(urlparse(url).path) + " " + text).lower()
    return sum(1 for w in _USEFUL if w in hay)


def _sitemap_urls(client: httpx.Client, base: str, robots_text: str) -> list[str]:
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_text) or [base + "/sitemap.xml"]
    found: list[str] = []
    for sm in maps[:2]:
        got = _get(client, sm)
        if not got:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", got[1])
        if "<sitemapindex" in got[1]:
            # Shopify / WordPress: one sitemap per kind; the "pages" one is what we want.
            for child in [u for u in locs if re.search(r"page|polic", u, re.I)][:3]:
                sub = _get(client, child)
                if sub:
                    found += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub[1])
        else:
            found += locs
    return found[:500]


def read_site(url: str, progress=None) -> list[dict]:
    """[{url, title, text}] of the site's useful pages. progress(done, total)."""
    base = normalize(url)
    if not base:
        raise SiteError("unreachable")
    started = time.monotonic()
    with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        home = _get(client, base)
        if not home:
            raise SiteError("unreachable")
        base = home[0].rstrip("/")
        origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"

        robots = RobotFileParser()
        rtxt = (_get(client, origin + "/robots.txt") or ("", ""))[1]
        robots.parse(rtxt.splitlines())
        allowed = lambda u: robots.can_fetch(USER_AGENT, u) if rtxt else True

        queue: list[tuple[int, int, str]] = []
        seen: set[str] = set()
        n = 0

        def add(u: str, score: int):
            nonlocal n
            u = urldefrag(urljoin(base + "/", u))[0].split("?")[0].rstrip("/")
            if not u.startswith("http") or not _same_site(u, base) or _SKIP.search(urlparse(u).path):
                return
            if u in seen or u == base:
                return
            seen.add(u)
            n += 1
            heapq.heappush(queue, (-score, n, u))

        for path in _KNOWN_PATHS:
            add(origin + path, 3)
        for u in _sitemap_urls(client, origin, rtxt):
            s = _score(u)
            if s:
                add(u, s)

        pages: list[dict] = []
        fillers: list[str] = []            # links with no telling words, for small sites
        texts: set[int] = set()
        done = 0

        def take(final_url: str, html: str, depth: int):
            p = _Page()
            try:
                p.feed(html)
            except Exception:  # noqa: BLE001 — broken html: keep what was read
                pass
            text = p.text()
            if len(text) >= 80 and hash(text) not in texts:
                texts.add(hash(text))
                pages.append({"url": final_url, "title": " ".join(p.title.split())[:200], "text": text[:PAGE_CHARS]})
            if depth < 2:
                for href, label in p.links:
                    s = _score(urljoin(final_url, href), label)
                    if s:
                        add(urljoin(final_url, href), s)
                    elif depth == 0:
                        fillers.append(urljoin(final_url, href))

        take(home[0], home[1], 0)
        while done < MAX_PAGES - 1 and time.monotonic() - started < MAX_SECONDS:
            if not queue:
                if len(pages) < 6 and fillers:          # small site: read a few more pages from the home page
                    for f in fillers[:10]:
                        add(f, 0)
                    fillers = []
                    if queue:
                        continue
                break
            _, _, u = heapq.heappop(queue)
            if not allowed(u):
                continue
            got = _get(client, u)
            done += 1
            if progress:
                progress(done, min(MAX_PAGES - 1, done + len(queue)))
            if got and _same_site(got[0], base):
                take(got[0], got[1], 1)
    if sum(len(p["text"]) for p in pages) < 300:
        raise SiteError("empty")
    return pages


# ── Writing the articles

_SYSTEM = """You write knowledge articles for a business's customer-service agent, using only the text of the business's own website (below).

Rules:
- Use only facts the website states clearly. If something is unclear, missing or contradicts itself, leave it out. Never guess or invent prices, times, phone numbers, addresses, names or rules.
- Never write placeholders, brackets or "[…]" — leave the fact out instead.
- One article per topic customers ask about: shipping and delivery, returns and exchanges, payment, contact details and opening hours, sizes, warranty, store locations, about the business, what it sells (categories and price range only — no single products), common questions. Skip a topic the site says nothing clear about.
- Skip privacy and legal text unless it tells customers something practical (for example cancellation rules).
- Write in {language}. Short, clear sentences, like explaining to a new employee: facts, prices, rules, steps. No marketing language.
- Each article at most about 1,500 characters. At most {max_articles} articles.
- "source": the address of the page most of the facts came from.

Reply with JSON only: {{"articles": [{{"title": "...", "body": "...", "source": "..."}}]}}"""

_BRACKETS = re.compile(r"\[[^\]\n]{1,80}\]")


def write_articles(tenant_id: str, url: str, pages: list[dict], language: str) -> list[dict]:
    parts, total = [], 0
    for p in pages:
        block = f"=== Page: {p['url']}\nTitle: {p['title']}\n\n{p['text']}\n"
        if total + len(block) > TOTAL_CHARS:
            break
        parts.append(block)
        total += len(block)
    system = _SYSTEM.format(language=LANGS.get(language, "English"), max_articles=MAX_ARTICLES)
    content = types.Content(role="user", parts=[types.Part(text=f"Website: {url}\n\n" + "\n".join(parts))])
    resp = gemini.generate([content], system, None, json_reply=True, timeout_seconds=90)
    usage.record_tokens(tenant_id, gemini.tokens_of(resp))
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        items = json.loads(raw).get("articles") or []
    except (ValueError, AttributeError):
        raise SiteError("failed") from None
    sources = {p["url"] for p in pages}
    out = []
    for a in items[:MAX_ARTICLES]:
        if not isinstance(a, dict):
            continue
        title = " ".join(str(a.get("title") or "").split())[:200]
        # Anything left uncertain is dropped, never shown as [brackets].
        body = "\n".join(ln for ln in str(a.get("body") or "").strip().splitlines() if not _BRACKETS.search(ln))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()[:5000]
        if title and len(body) >= 20:
            src = str(a.get("source") or "")
            out.append({"title": title, "body": body, "source": src if src in sources else None})
    return out


# ── The job

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set(import_id: str, values: dict, only_when: str | None = None) -> list[dict]:
    f = {"id": f"eq.{import_id}"}
    if only_when:
        f["status"] = only_when
    return db.update("site_imports", f, {**values, "updated_at": _now()})


def handle(payload: dict) -> str:
    """Worker job: read the site, write the suggestions."""
    import_id = payload["import_id"]
    row = db.select_one("site_imports", {"select": "id,tenant_id,url,language,status", "id": f"eq.{import_id}"})
    if not row or row["status"] not in ("queued", "reading"):
        return "skipped"
    running = "in.(queued,reading,writing)"        # dismissed meanwhile → stop writing
    _set(import_id, {"status": "reading"}, running)
    last = [0.0]

    def progress(done: int, total: int):
        if time.monotonic() - last[0] > 1.5:
            last[0] = time.monotonic()
            _set(import_id, {"pages_done": done, "pages_total": total}, running)

    try:
        pages = read_site(row["url"], progress)
        if not _set(import_id, {"status": "writing", "pages_read": len(pages)}, running):
            return "dismissed"
        articles = write_articles(row["tenant_id"], row["url"], pages, row["language"])
        if not articles:
            raise SiteError("empty")
    except SiteError as e:
        _set(import_id, {"status": "failed", "error": e.code}, running)
        return f"failed: {e.code}"
    except Exception as e:  # noqa: BLE001
        errors.report("job", "site_import", e, tenant_id=row["tenant_id"])
        _set(import_id, {"status": "failed", "error": "failed"}, running)
        return "failed"
    _set(import_id, {"status": "ready", "suggestions": articles}, running)
    return f"{len(articles)} articles from {len(pages)} pages"
