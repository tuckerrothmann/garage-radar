"""Browser-impersonating HTTP client for Cloudflare-protected sources."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from curl_cffi import requests as curl_requests

from garage_radar.sources.base import RawPage
from garage_radar.sources.shared.rate_limiter import get_limiter

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class ImpersonatedHttpClient:
    """Async wrapper around curl_cffi requests with Chrome impersonation."""

    def __init__(
        self,
        source_name: str,
        domain: str,
        rate: float,
        timeout: float = 30.0,
        impersonate: str = "chrome124",
    ) -> None:
        self.source_name = source_name
        self.domain = domain
        self.rate_limiter = get_limiter(domain, rate=rate)
        self.timeout = timeout
        self.impersonate = impersonate

    async def __aenter__(self) -> ImpersonatedHttpClient:
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, url: str, referer: str = "") -> RawPage:
        headers = {"Referer": referer} if referer else None

        for attempt in range(_MAX_RETRIES + 1):
            await self.rate_limiter.acquire()
            try:
                response = await asyncio.to_thread(
                    curl_requests.get,
                    url,
                    headers=headers,
                    impersonate=self.impersonate,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
            except Exception as exc:
                backoff = _BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Impersonated fetch failed for %s: %s. Retry %d/%d after %.1fs.",
                    url,
                    exc,
                    attempt + 1,
                    _MAX_RETRIES,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue

            if response.status_code in _RETRYABLE_STATUSES:
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

            content_type = "json" if "application/json" in response.headers.get("content-type", "") else "html"
            return RawPage(
                source=self.source_name,
                url=str(response.url),
                fetched_at=datetime.now(UTC),
                content=response.text,
                content_type=content_type,
                status_code=response.status_code,
            )

        logger.error("Permanently failed to fetch %s after %d attempts.", url, _MAX_RETRIES + 1)
        return RawPage(
            source=self.source_name,
            url=url,
            fetched_at=datetime.now(UTC),
            content="",
            content_type="html",
            status_code=0,
        )
