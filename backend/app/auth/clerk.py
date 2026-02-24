"""Clerk JWT verification — uses httpx (async) to fetch JWKS, avoiding PyJWKClient's
synchronous `requests` dependency which fails on macOS due to SSL certificate issues."""

import json
import time
from typing import Any

import httpx
import jwt

from app.config import settings

# In-memory JWKS cache: {"keys": [...], "fetched_at": float}
_jwks_cache: dict[str, Any] = {}
_CACHE_TTL = 3600  # 1 hour


async def _fetch_jwks() -> list[dict]:
    """Fetch JWKS from Clerk and cache the result for _CACHE_TTL seconds."""
    now = time.monotonic()
    if _jwks_cache.get("keys") and (now - _jwks_cache.get("fetched_at", 0)) < _CACHE_TTL:
        return _jwks_cache["keys"]

    async with httpx.AsyncClient(verify=True, timeout=10.0) as client:
        resp = await client.get(settings.CLERK_JWKS_URL)
        resp.raise_for_status()
        data = resp.json()

    keys = data.get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk-issued JWT and return the decoded payload.

    Uses httpx (async, respects system certs) instead of PyJWKClient's
    synchronous `requests` backend.  Raises jwt.InvalidTokenError on any failure.
    """
    try:
        # Decode header without verification to get the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        keys = await _fetch_jwks()

        # Find the matching key
        jwk = next((k for k in keys if k.get("kid") == kid), None)
        if jwk is None:
            # Key not in cache — force a refresh and try once more
            _jwks_cache.clear()
            keys = await _fetch_jwks()
            jwk = next((k for k in keys if k.get("kid") == kid), None)
            if jwk is None:
                raise jwt.InvalidTokenError(f"No matching key found for kid={kid!r}")

        # Construct the public key from the JWK
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,  # Clerk tokens use azp, not aud
            },
        )
        return payload

    except jwt.InvalidTokenError:
        raise
    except Exception as exc:
        raise jwt.InvalidTokenError(f"Token verification failed: {exc}") from exc


async def get_clerk_user(clerk_user_id: str) -> dict | None:
    """Fetch a user's details from the Clerk API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None
