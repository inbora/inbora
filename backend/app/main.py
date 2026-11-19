from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import get_settings
from .routers import admin, me

settings = get_settings()

app = FastAPI(title="Inbora API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Render's health check. Also reports whether Supabase is reachable."""
    return {"status": "ok", "database": "ok" if db.ping() else "unreachable"}


app.include_router(me.router)
app.include_router(admin.router)
