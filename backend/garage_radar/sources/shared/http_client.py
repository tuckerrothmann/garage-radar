"""
Garage Radar — Shared async HTTP client.

Wraps httpx with:
  - Rate limiting (via RateLimiter)
  - UA rotation
  - Retry with exponential backoff on transient errors
  - Respect for Retry-After headers on 429

Usage:
    async with HttpClient(domain="bringatrailer.com", rate=0.33) as client:
        raw_page = await client.get("https://bringatrailer.com/listing/...")
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from garage_radar.sources.base import RawPage
from garage_radar.sources.shared.rate_limiter import get_limiter
from garage_radar.sources.shared.ua_rotation import get_headers

logger = logging.getLogger(__name__)

# Transient HTTP status codes that warrant a retry
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds; doubles each retry


class HttpClient:
    """
    Async HTTP client scoped to a single domain.
    Use as an async context manager.
    """

    def __init__(
        self,
        source_name: str,
        domain: str,
        rate: float = 0.33,
        timeout: float = 30.0,
    ):
        self.source_name = source_name
        self.domain = domain
        self.rate_limiter = get_limiter(domain, rate=rate)
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HttpClient":
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(self.timeout),
            http2=True,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, referer: str = "") -> RawPage:
        """
        Fetch a URL with rate limiting + retry.
        Always returns a RawPage — on persistent failure, returns status_code=0 with empty content.
        """
        assert self._client is not None, "Use HttpClient as an async context manager."

        headers = get_headers(referer=referer)
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            await self.rate_limiter.acquire()

            try:
                response = await self._client.get(url, headers=headers)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", _BACKOFF_BASE ** (attempt + 1)))
                    logger.warning(
                        "Rate limited by %s (429). Sleeping %ss.", self.domain, retry_after
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code in _RETRY_STATUSES:
                    backoff = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "HTTP %s from %s. Retry %d/%d after %.1fs.",
                        response.status_code,
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

                content_type = "html"
                if "application/json" in response.headers.get("content-type", ""):
                    content_type = "json"

                return RawPage(
                    source=self.source_name,
                    url=str(response.url),
                    fetched_at=datetime.utcnow(),
                    content=response.text,
                    content_type=content_type,
                    status_code=response.status_code,
                )

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                backoff = _BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Network error fetching %s: %s. Retry %d/%d after %.1fs.",
                    url,
                    exc,
                    attempt + 1,
                    _MAX_RETRIES,
                    backoff,
                )
                last_exc = exc
                await asyncio.sleep(backoff)

        logger.error("Permanently failed to fetch %s after %d attempts.", url, _MAX_RETRIES + 1)
        return RawPage(
            source=self.source_name,
            url=url,
            fetched_at=datetime.utcnow(),
            content="",
            content_type="html",
            status_code=0,
        )
