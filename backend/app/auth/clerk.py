"""Clerk JWT verification using their JWKS endpoint."""

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.CLERK_JWKS_URL, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk-issued JWT and return the decoded payload.
    Raises jwt.InvalidTokenError on failure.
    """
    client = get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_exp": True},
    )
    return payload


async def get_clerk_user(clerk_user_id: str) -> dict | None:
    """Fetch a user's details from the Clerk API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None
