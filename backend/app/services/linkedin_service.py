"""
Apify-based LinkedIn enrichment service.

Resolves LinkedIn profile URLs using name + company via the
harvestapi/linkedin-profile-search-by-name actor (pay-per-event).

Fetches recent posts via the bestscrapers/linkedin-post-scraper actor
($8/1,000 posts, no cookies required).

Requires APIFY_API_TOKEN in .env.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2"
_PROFILE_ACTOR = "harvestapi~linkedin-profile-search-by-name"
_POSTS_ACTOR = "bestscrapers~linkedin-post-scraper"
_TIMEOUT = 120

_api_available: bool | None = None


async def is_api_available() -> bool:
    """
    Quick health check: verify the Apify token is set and the API is reachable.
    Caches the result for the lifetime of the process (reset on restart).
    """
    global _api_available
    if _api_available is not None:
        return _api_available

    if not settings.APIFY_API_TOKEN:
        _api_available = False
        return False

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{_APIFY_BASE}/users/me",
                params={"token": settings.APIFY_API_TOKEN},
            )
            _api_available = resp.is_success
    except (httpx.TimeoutException, httpx.ConnectError):
        _api_available = False

    if not _api_available:
        logger.warning("Apify API is unreachable — LinkedIn enrichment will be skipped")
    return _api_available


def reset_availability() -> None:
    """Allow re-checking on next call (e.g. after config change)."""
    global _api_available
    _api_available = None


def _split_name(full_name: str) -> tuple[str, str]:
    """Split a full name into (firstName, lastName). Last name defaults to first if single word."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return (full_name.strip(), full_name.strip())
    return (parts[0], " ".join(parts[1:]))


async def find_linkedin_profile(
    name: str,
    company: str | None = None,
) -> str | None:
    """
    Resolve a LinkedIn profile URL using name + company via Apify actor.
    Returns the profile URL or None if not found.
    """
    if not settings.APIFY_API_TOKEN:
        return None
    if not await is_api_available():
        return None

    first_name, last_name = _split_name(name)

    payload: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
        "profileScraperMode": "Short",
        "maxItems": 1,
    }
    if company:
        payload["currentCompanies"] = [company.lower()]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_APIFY_BASE}/acts/{_PROFILE_ACTOR}/run-sync-get-dataset-items",
                params={"token": settings.APIFY_API_TOKEN},
                json=payload,
            )
    except (httpx.TimeoutException, httpx.ConnectError):
        logger.warning("Apify timeout for profile lookup: %s", name)
        return None

    if resp.status_code == 408:
        logger.warning("Apify actor timed out for profile lookup: %s", name)
        return None
    if resp.status_code == 429:
        logger.warning("Apify rate limit hit for profile lookup: %s", name)
        return None
    if not resp.is_success:
        logger.error("Apify profile lookup failed (%d): %s", resp.status_code, resp.text[:200])
        return None

    try:
        data = resp.json()
    except Exception:
        logger.error("Apify returned non-JSON response for: %s", name)
        return None

    if isinstance(data, list) and data:
        url = data[0].get("linkedinUrl")
        if url and "linkedin.com" in url:
            return url
    return None


async def find_linkedin_profile_by_email(email: str) -> str | None:
    """Apify profile finder uses name+company, not email — always returns None."""
    return None


async def find_linkedin_profile_by_name(
    name: str,
    company: str | None = None,
) -> str | None:
    """Alias for find_linkedin_profile for backward compat."""
    return await find_linkedin_profile(name, company)


async def fetch_recent_posts(
    linkedin_url: str,
    count: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch recent posts for a LinkedIn profile using
    bestscrapers/linkedin-post-scraper ($8/1,000 posts).
    Returns a list of dicts with keys: post_url, text, posted_at.
    """
    if not settings.APIFY_API_TOKEN:
        return []
    if not await is_api_available():
        return []

    payload = {"linkedin_url": linkedin_url, "start": 0}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_APIFY_BASE}/acts/{_POSTS_ACTOR}/run-sync-get-dataset-items",
                params={"token": settings.APIFY_API_TOKEN},
                json=payload,
            )
    except (httpx.TimeoutException, httpx.ConnectError):
        logger.warning("Apify timeout for posts: %s", linkedin_url)
        return []

    if resp.status_code == 408:
        logger.warning("Apify actor timed out for posts: %s", linkedin_url)
        return []
    if resp.status_code == 429:
        logger.warning("Apify rate limit hit for posts: %s", linkedin_url)
        return []
    if not resp.is_success:
        logger.error("Apify posts fetch failed (%d): %s", resp.status_code, resp.text[:200])
        return []

    try:
        data = resp.json()
    except Exception:
        logger.error("Apify returned non-JSON response for posts: %s", linkedin_url)
        return []

    # The actor returns [{data: [...posts...], message, paging}]
    raw_posts: list[dict] = []
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict) and "data" in item:
            raw_posts = item["data"]
        elif isinstance(item, dict) and "post_url" in item:
            raw_posts = data

    posts: list[dict[str, Any]] = []
    for p in raw_posts[:count]:
        posted_at = None
        if p.get("posted"):
            try:
                posted_at = datetime.strptime(p["posted"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except (TypeError, ValueError):
                pass

        posts.append({
            "post_url": p.get("post_url"),
            "text": p.get("text", ""),
            "posted_at": posted_at,
        })

    return posts
