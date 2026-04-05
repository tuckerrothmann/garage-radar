"""Dataclasses shared by external reference providers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ReferenceSource:
    name: str
    url: str
    license: str | None = None


@dataclass
class ReferenceSection:
    title: str
    summary: str
    source_name: str
    source_url: str | None = None


@dataclass
class ReferenceProfile:
    provider: str
    title: str
    canonical_url: str | None = None
    image_url: str | None = None
    summary: str | None = None
    facts: dict[str, str] = field(default_factory=dict)
    sections: list[ReferenceSection] = field(default_factory=list)
    sources: list[ReferenceSource] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
