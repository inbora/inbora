from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, errors, worker_loop
from .config import get_settings
from .routers import (admin, agent, billing, channels, inbox, knowledge, me, public, push, widget,
                      zernio_webhook)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.embedded_worker:
        worker_loop.start_embedded()
    yield
    worker_loop.stop_embedded()


app = FastAPI(title="Inbora API", version="0.8.0", lifespan=lifespan)


class SplitCORS:
    """The website chat (/widget/...) is called from any customer's site; the
    rest of the API only from the Inbora panel."""

    def __init__(self, app):
        self.public = CORSMiddleware(app, allow_origins=["*"], allow_methods=["GET", "POST"],
                                     allow_headers=["Content-Type"], allow_credentials=False)
        self.panel = CORSMiddleware(app, allow_origins=settings.cors_origins, allow_methods=["*"],
                                    allow_headers=["*"], allow_credentials=False)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/widget/"):
            return await self.public(scope, receive, send)
        return await self.panel(scope, receive, send)


app.add_middleware(SplitCORS)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Anything not handled: log it, record it for the Super-admin page, and
    answer 500 (the traceback stays in the Render logs too)."""
    import traceback
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    route = request.scope.get("route")
    where = f"{request.method} {getattr(route, 'path', request.url.path)}"
    errors.report("api", where, exc)
    return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)


@app.get("/health")
def health():
    """Render's health check. Also reports whether Supabase is reachable, and why not."""
    ok, reason = db.check()
    out = {
        "status": "ok",
        "database": "ok" if ok else "unreachable",
        "agent": "ok" if settings.gemini_api_key else "missing GEMINI_API_KEY",
        "whatsapp_instagram_email": "ok" if (settings.zernio_api_key and settings.zernio_webhook_secret)
                              else "missing ZERNIO_API_KEY / ZERNIO_WEBHOOK_SECRET",
    }
    if not ok:
        out["reason"] = reason
    return out


app.include_router(me.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(public.router)
app.include_router(agent.router)
app.include_router(knowledge.router)
app.include_router(channels.router)
app.include_router(inbox.router)
app.include_router(push.router)
app.include_router(widget.router)
app.include_router(zernio_webhook.router)
