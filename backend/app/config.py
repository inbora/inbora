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

    # Used from Step 2 onward
    gemini_api_key: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.web_url.split(",") if o.strip()]

    @property
    def rest_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
