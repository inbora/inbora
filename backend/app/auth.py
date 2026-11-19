"""Verify the Supabase access token sent by the web panel.

The panel sends `Authorization: Bearer <access_token>`. New Supabase projects
sign tokens with asymmetric keys (ES256/RS256) published at a JWKS endpoint;
older projects use a shared HS256 secret. Both are handled."""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import get_settings

_bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        url = f"{get_settings().supabase_base}/auth/v1/.well-known/jwks.json"
        _jwks = jwt.PyJWKClient(url, cache_keys=True)
    return _jwks


def _decode(token: str) -> dict:
    s = get_settings()
    alg = jwt.get_unverified_header(token).get("alg", "")
    if alg == "HS256":
        if not s.supabase_jwt_secret:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "HS256 token but SUPABASE_JWT_SECRET is not set")
        key = s.supabase_jwt_secret
    else:
        key = _jwks_client().get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=[alg], audience="authenticated")


@dataclass
class CurrentUser:
    id: str
    email: str
    is_super_admin: bool


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        claims = _decode(creds.credentials)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user_id = claims.get("sub")
    profile = db.select_one("profiles", {"select": "email,is_super_admin", "id": f"eq.{user_id}"})
    if profile is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No profile for this user")
    return CurrentUser(
        id=user_id,
        email=profile["email"],
        is_super_admin=bool(profile["is_super_admin"]),
    )


def super_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super-admin only")
    return user
