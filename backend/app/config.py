"""All settings come from environment variables (set them on Render).
For local development, put them in backend/.env — see .env.example."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    # Only needed if your project still signs tokens with the legacy shared
    # secret (HS256). New projects use signing keys, verified via JWKS.
    supabase_jwt_secret: str = ""

    # Web panel origin, for CORS (comma-separated if more than one)
    web_url: str = "http://localhost:3000"

    # Agent (Step 2)
    gemini_api_key: str = ""
    # Tried in order; if one fails or is overloaded, the next one answers.
    gemini_models: str = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3-flash-preview"
    # A model that takes longer than this is abandoned and the next one is tried.
    gemini_timeout_seconds: float = 20
    # Total time one reply may take (all models, all tool rounds) before the
    # customer gets the "technical problem" message instead.
    agent_deadline_seconds: float = 50

    # A conversation the team took over goes back to the agent when the
    # customer writes again after this many hours without a team reply.
    handback_hours: float = 1

    # Links in alerts point here.
    app_url: str = "https://app.inbora.ai"

    # Alerts to the business's team (Step 4). Each is skipped when not set.
    resend_api_key: str = ""
    alerts_from: str = "Inbora <alerts@inbora.ai>"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:contact@inbora.ai"

    # WhatsApp and Instagram through Zernio (Step 5)
    zernio_api_key: str = ""
    zernio_webhook_secret: str = ""
    zernio_api_base: str = "https://zernio.com/api/v1"

    # Background worker. true = runs inside the API process (no extra service).
    embedded_worker: bool = True
    worker_concurrency: int = 4

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.web_url.split(",") if o.strip()]

    @property
    def supabase_base(self) -> str:
        # Tolerate a pasted URL with a trailing slash or /rest/v1.
        return self.supabase_url.strip().rstrip("/").removesuffix("/rest/v1")

    @property
    def rest_url(self) -> str:
        return f"{self.supabase_base}/rest/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
