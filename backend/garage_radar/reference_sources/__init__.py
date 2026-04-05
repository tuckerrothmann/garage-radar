"""Reference source integrations for vehicle profiles."""

from garage_radar.reference_sources.base import (
    ReferenceProfile,
    ReferenceSection,
    ReferenceSource,
)
from garage_radar.reference_sources.wikimedia import WikimediaVehicleProfileProvider

__all__ = [
    "ReferenceProfile",
    "ReferenceSection",
    "ReferenceSource",
    "WikimediaVehicleProfileProvider",
]
