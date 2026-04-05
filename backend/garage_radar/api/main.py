"""
Compatibility entrypoint for the FastAPI app.

`garage_radar.api` already exposes `app`, but several dev commands point at
`garage_radar.api.main:app`. Re-export it here so both forms work.
"""

from garage_radar.api import app, create_app

__all__ = ["app", "create_app"]
