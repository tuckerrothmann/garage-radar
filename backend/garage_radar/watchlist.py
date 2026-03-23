"""
Garage Radar — Watchlist configuration loader.

Reads config/watchlist.yaml (relative to project root) and exposes a list of
WatchedVehicle objects that drive which makes/models are crawled.

If watchlist.yaml is not found, falls back to watchlist.example.yaml.
If neither exists, returns an empty list (crawlers will skip quietly).

Environment variable WATCHLIST_PATH overrides the default file location.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Project root is 3 levels up from this file: backend/garage_radar/watchlist.py
_PROJECT_ROOT = Path(__file__).parents[2]
_DEFAULT_PATH = _PROJECT_ROOT / "config" / "watchlist.yaml"
_FALLBACK_PATH = _PROJECT_ROOT / "config" / "watchlist.example.yaml"


@dataclass
class WatchedVehicle:
    make: str
    model: str
    year_min: int
    year_max: int
    # Optional per-source search term overrides
    search_override: dict[str, str] = field(default_factory=dict)

    def search_query(self, source: str) -> str:
        """Return the search query string for the given source."""
        if source in self.search_override:
            return self.search_override[source]
        return f"{self.make} {self.model}"


def get_watched_vehicles() -> list[WatchedVehicle]:
    """
    Load and return the list of watched vehicles from config/watchlist.yaml.

    Returns an empty list if no configuration file is found.
    """
    env_path = os.environ.get("WATCHLIST_PATH")
    if env_path:
        path = Path(env_path)
    elif _DEFAULT_PATH.exists():
        path = _DEFAULT_PATH
    elif _FALLBACK_PATH.exists():
        logger.warning(
            "watchlist.yaml not found; using watchlist.example.yaml. "
            "Copy config/watchlist.example.yaml to config/watchlist.yaml to customise."
        )
        path = _FALLBACK_PATH
    else:
        logger.warning(
            "No watchlist configuration found. Crawlers will not search for any vehicles. "
            "Create config/watchlist.yaml based on config/watchlist.example.yaml."
        )
        return []

    try:
        import yaml  # PyYAML — optional dep; only needed at runtime
    except ImportError:
        logger.error(
            "PyYAML is not installed. Cannot load watchlist. "
            "Run: pip install pyyaml"
        )
        return []

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception:
        logger.exception("Failed to parse watchlist file: %s", path)
        return []

    if not isinstance(data, dict) or "vehicles" not in data:
        logger.error("watchlist.yaml must contain a top-level 'vehicles' list.")
        return []

    vehicles: list[WatchedVehicle] = []
    for entry in data.get("vehicles") or []:
        try:
            vehicles.append(
                WatchedVehicle(
                    make=str(entry["make"]),
                    model=str(entry["model"]),
                    year_min=int(entry["year_min"]),
                    year_max=int(entry["year_max"]),
                    search_override=dict(entry.get("search_override") or {}),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping invalid watchlist entry %r: %s", entry, exc)

    logger.info("Watchlist loaded: %d vehicles from %s", len(vehicles), path)
    return vehicles
