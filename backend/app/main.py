from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, worker_loop
from .config import get_settings
from .routers import admin, agent, me

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.embedded_worker:
        worker_loop.start_embedded()
    yield
    worker_loop.stop_embedded()


app = FastAPI(title="Inbora API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Render's health check. Also reports whether Supabase is reachable, and why not."""
    ok, reason = db.check()
    out = {
        "status": "ok",
        "database": "ok" if ok else "unreachable",
        "agent": "ok" if settings.gemini_api_key else "missing GEMINI_API_KEY",
    }
    if not ok:
        out["reason"] = reason
    return out


app.include_router(me.router)
app.include_router(admin.router)
app.include_router(agent.router)
