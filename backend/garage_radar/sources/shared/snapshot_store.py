"""
Garage Radar — Raw HTML/JSON snapshot store.

Writes fetched pages to disk for replay and debugging.
Directory layout: {base}/{source}/{YYYY-MM-DD}/{slug}.html

All writes are best-effort — a store failure never fails the crawler.
"""
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from garage_radar.sources.base import RawPage

logger = logging.getLogger(__name__)


def _url_to_slug(url: str) -> str:
    """Convert a URL to a safe filename slug."""
    # Strip scheme and collapse unsafe chars
    slug = re.sub(r"https?://", "", url)
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", slug)
    slug = slug.strip("_")[:120]  # cap length
    # Append short hash to avoid collisions
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{slug}_{h}"


class SnapshotStore:
    """Local filesystem snapshot store."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _path_for(self, raw: RawPage) -> Path:
        date_str = raw.fetched_at.strftime("%Y-%m-%d")
        ext = "json" if raw.content_type == "json" else "html"
        slug = _url_to_slug(raw.url)
        return self.base_path / raw.source / date_str / f"{slug}.{ext}"

    def write(self, raw: RawPage) -> Optional[str]:
        """
        Write raw page content to disk.
        Returns the relative path string, or None on failure.
        """
        if not raw.content:
            return None

        try:
            path = self._path_for(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw.content, encoding="utf-8")
            logger.debug("Snapshot written: %s", path)
            return str(path)
        except OSError as exc:
            logger.warning("Failed to write snapshot for %s: %s", raw.url, exc)
            return None

    def read(self, path: str) -> Optional[str]:
        """Read a previously stored snapshot. Returns content or None."""
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return None

    def exists(self, raw: RawPage) -> bool:
        """Check if a snapshot already exists for this page (today's date)."""
        return self._path_for(raw).exists()


_store: Optional[SnapshotStore] = None


def get_snapshot_store() -> SnapshotStore:
    global _store
    if _store is None:
        from garage_radar.config import get_settings
        settings = get_settings()
        _store = SnapshotStore(settings.snapshot_store_path)
    return _store
