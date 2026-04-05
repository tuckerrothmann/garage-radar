"""Wikimedia-backed vehicle profile enrichment."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, TypeVar

import httpx
from bs4 import BeautifulSoup

from garage_radar.config import get_settings
from garage_radar.reference_sources.base import (
    ReferenceProfile,
    ReferenceSection,
    ReferenceSource,
)

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_DISALLOWED_SECTION_TITLES = {
    "see also",
    "references",
    "external links",
    "notes",
    "citations",
    "sources",
}
_SECTION_PRIORITY = (
    "history",
    "generation",
    "design",
    "development",
    "specification",
    "powertrain",
    "variant",
    "technology",
    "engineering",
    "interior",
    "facelift",
    "reception",
    "legacy",
    "safety",
    "motorsport",
    "production",
    "special",
    "overview",
)
_MAX_SECTION_COUNT = 6
_CACHE_VERSION = 3
_WIKIDATA_FACT_PROPERTIES = {
    "P176": "Manufacturer",
    "P495": "Country of origin",
    "P571": "Introduced",
    "P576": "Ended",
    "P856": "Official website",
}
_INFOBOX_FACT_ALIASES = {
    "manufacturer": "Manufacturer",
    "production": "Production",
    "model years": "Model years",
    "assembly": "Assembly",
    "designer": "Designer",
    "class": "Vehicle class",
    "body style": "Body style",
    "layout": "Layout",
    "platform": "Platform",
    "engine": "Engine",
    "powertrain": "Powertrain",
    "transmission": "Transmission",
    "predecessor": "Predecessor",
    "successor": "Successor",
    "related": "Related",
}
T = TypeVar("T")


class WikimediaVehicleProfileProvider:
    """Fetch and cache encyclopedic model information from Wikimedia APIs."""

    provider_name = "Wikimedia"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)

    async def fetch_profile(
        self,
        make: str,
        model: str,
        *,
        year: int | None = None,
    ) -> ReferenceProfile | None:
        cache_path = self._cache_path(make, model)
        miss_cache_path = self._miss_cache_path(make, model)
        cached = self._load_cache(cache_path)
        if cached is not None:
            return cached
        stale_cached = self._load_cache(cache_path, allow_stale=True)
        if self._load_miss_cache(miss_cache_path):
            return stale_cached

        try:
            async with asyncio.timeout(self.settings.reference_profile_budget_s):
                async with httpx.AsyncClient(
                    headers={"User-Agent": self.settings.reference_user_agent},
                    timeout=self.settings.reference_request_timeout_s,
                    follow_redirects=True,
                ) as client:
                    page = await self._resolve_page(client, make, model, year)
                    if page is None:
                        self._write_miss_cache(miss_cache_path)
                        return stale_cached

                    infobox_facts, sections, wikidata_facts = await self._fetch_profile_parts(
                        client,
                        page["title"],
                        page.get("wikibase_item"),
                    )

            facts = dict(infobox_facts)
            for key, value in wikidata_facts.items():
                facts.setdefault(key, value)

            profile = ReferenceProfile(
                provider=self.provider_name,
                title=page["title"],
                canonical_url=page.get("canonical_url"),
                image_url=page.get("image_url"),
                summary=page.get("summary"),
                facts=facts,
                sections=sections,
                sources=[
                    ReferenceSource(
                        name="Wikipedia",
                        url=page.get("canonical_url")
                        or f"https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}",
                        license="CC BY-SA 4.0",
                    ),
                    ReferenceSource(
                        name="Wikidata",
                        url=f"https://www.wikidata.org/wiki/{page['wikibase_item']}",
                        license="CC0",
                    )
                    if page.get("wikibase_item")
                    else None,
                ],
            )
            profile.sources = [source for source in profile.sources if source is not None]
            self._write_cache(cache_path, profile)
            self._clear_miss_cache(miss_cache_path)
            return profile
        except TimeoutError:
            self.logger.warning(
                "Timed out fetching Wikimedia vehicle profile for %s %s within %.1fs",
                make,
                model,
                self.settings.reference_profile_budget_s,
            )
            self._write_miss_cache(miss_cache_path)
            return stale_cached
        except (httpx.HTTPError, OSError, ValueError) as exc:
            self.logger.warning(
                "Failed to fetch Wikimedia vehicle profile for %s %s: %s",
                make,
                model,
                exc,
            )
            self._write_miss_cache(miss_cache_path)
            return stale_cached

    async def _fetch_profile_parts(
        self,
        client: httpx.AsyncClient,
        page_title: str,
        wikibase_item: str | None,
    ) -> tuple[dict[str, str], list[ReferenceSection], dict[str, str]]:
        parts = await asyncio.gather(
            self._fetch_infobox_facts(client, page_title),
            self._fetch_section_summaries(client, page_title),
            self._fetch_wikidata_facts(client, wikibase_item),
            return_exceptions=True,
        )
        infobox_facts = self._coerce_part(parts[0], default={}, label="infobox facts", page_title=page_title)
        sections = self._coerce_part(parts[1], default=[], label="section summaries", page_title=page_title)
        wikidata_facts = self._coerce_part(parts[2], default={}, label="Wikidata facts", page_title=page_title)
        return infobox_facts, sections, wikidata_facts

    async def _resolve_page(
        self,
        client: httpx.AsyncClient,
        make: str,
        model: str,
        year: int | None,
    ) -> dict[str, Any] | None:
        for candidate in self._candidate_titles(make, model, year):
            page = await self._fetch_page_summary(client, candidate)
            if page is not None and self._is_relevant_page(page, make, model):
                return page

        for search_title in await self._search_titles(client, make, model):
            page = await self._fetch_page_summary(client, search_title)
            if page is not None and self._is_relevant_page(page, make, model):
                return page
        return None

    async def _fetch_page_summary(
        self,
        client: httpx.AsyncClient,
        title: str,
    ) -> dict[str, Any] | None:
        payload = await self._request_json(
            client,
            _WIKIPEDIA_API,
            {
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "redirects": 1,
                "prop": "extracts|pageprops|pageimages|info",
                "exintro": 1,
                "explaintext": 1,
                "inprop": "url",
                "piprop": "thumbnail",
                "pithumbsize": 900,
                "titles": title,
            },
        )
        pages = payload.get("query", {}).get("pages", [])
        if not pages:
            return None
        page = pages[0]
        if page.get("missing"):
            return None

        return {
            "title": page["title"],
            "summary": self._clean_text(page.get("extract")),
            "wikibase_item": page.get("pageprops", {}).get("wikibase_item"),
            "canonical_url": page.get("fullurl"),
            "image_url": page.get("thumbnail", {}).get("source"),
        }

    async def _search_titles(
        self,
        client: httpx.AsyncClient,
        make: str,
        model: str,
    ) -> list[str]:
        payload = await self._request_json(
            client,
            _WIKIPEDIA_API,
            {
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "list": "search",
                "srlimit": 5,
                "srsearch": f"\"{make} {model}\" automobile",
            },
        )
        return [entry["title"] for entry in payload.get("query", {}).get("search", [])]

    async def _fetch_infobox_facts(
        self,
        client: httpx.AsyncClient,
        page_title: str,
    ) -> dict[str, str]:
        payload = await self._request_json(
            client,
            _WIKIPEDIA_API,
            {
                "action": "parse",
                "format": "json",
                "page": page_title,
                "prop": "text",
                "section": 0,
            },
        )
        html = payload.get("parse", {}).get("text", {}).get("*", "")
        return self._extract_infobox_facts(html)

    async def _fetch_section_summaries(
        self,
        client: httpx.AsyncClient,
        page_title: str,
    ) -> list[ReferenceSection]:
        toc_payload = await self._request_json(
            client,
            _WIKIPEDIA_API,
            {
                "action": "parse",
                "format": "json",
                "page": page_title,
                "prop": "tocdata",
            },
        )
        parse_payload = toc_payload.get("parse") or {}
        tocdata = parse_payload.get("tocdata") or {}
        sections = tocdata.get("sections") or []
        chosen = self._choose_sections(sections)

        results = await asyncio.gather(
            *(self._fetch_section_summary(client, page_title, section) for section in chosen),
            return_exceptions=True,
        )
        sections_out: list[ReferenceSection] = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.warning(
                    "Failed to fetch Wikimedia section summary for %s: %s",
                    page_title,
                    result,
                )
                continue
            if result is not None:
                sections_out.append(result)
        return sections_out

    async def _fetch_section_summary(
        self,
        client: httpx.AsyncClient,
        page_title: str,
        section: dict[str, Any],
    ) -> ReferenceSection | None:
        payload = await self._request_json(
            client,
            _WIKIPEDIA_API,
            {
                "action": "parse",
                "format": "json",
                "page": page_title,
                "prop": "text",
                "section": section["index"],
            },
        )
        html = payload.get("parse", {}).get("text", {}).get("*", "")
        summary = self._html_to_summary(html)
        if not summary:
            return None
        return ReferenceSection(
            title=unescape(section["line"]),
            summary=summary,
            source_name="Wikipedia",
            source_url=(
                f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
                f"#{section.get('anchor') or ''}"
            ).rstrip("#"),
        )

    async def _fetch_wikidata_facts(
        self,
        client: httpx.AsyncClient,
        entity_id: str | None,
    ) -> dict[str, str]:
        if not entity_id:
            return {}

        payload = await self._request_json(
            client,
            _WIKIDATA_API,
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": entity_id,
                "props": "labels|descriptions|claims",
                "languages": "en",
            },
        )
        entity = payload.get("entities", {}).get(entity_id, {})
        claims = entity.get("claims", {})

        referenced_ids: set[str] = set()
        for property_id in ("P176", "P495"):
            for claim in claims.get(property_id, []):
                entity_value = self._claim_entity_id(claim)
                if entity_value:
                    referenced_ids.add(entity_value)

        label_lookup: dict[str, str] = {}
        if referenced_ids:
            label_payload = await self._request_json(
                client,
                _WIKIDATA_API,
                {
                    "action": "wbgetentities",
                    "format": "json",
                    "ids": "|".join(sorted(referenced_ids)),
                    "props": "labels",
                    "languages": "en",
                },
            )
            for ref_id, ref_entity in label_payload.get("entities", {}).items():
                label = ref_entity.get("labels", {}).get("en", {}).get("value")
                if label:
                    label_lookup[ref_id] = label

        facts: dict[str, str] = {}
        description = entity.get("descriptions", {}).get("en", {}).get("value")
        if description:
            facts["Wikidata description"] = description

        for property_id, label in _WIKIDATA_FACT_PROPERTIES.items():
            values = self._claim_values(claims.get(property_id, []), label_lookup)
            if values:
                facts[label] = ", ".join(values)
        return facts

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _choose_sections(self, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        top_level_sections = [
            section
            for section in sections
            if section.get("tocLevel") == 1
            and section.get("line")
            and unescape(section["line"]).strip().lower() not in _DISALLOWED_SECTION_TITLES
        ]
        if not top_level_sections:
            return []

        def section_rank(section: dict[str, Any]) -> tuple[int, int]:
            line = unescape(section["line"]).lower()
            for rank, keyword in enumerate(_SECTION_PRIORITY):
                if keyword in line:
                    return (rank, int(section["index"]))
            return (len(_SECTION_PRIORITY), int(section["index"]))

        ordered = sorted(top_level_sections, key=section_rank)
        selected = ordered[:_MAX_SECTION_COUNT]
        return sorted(selected, key=lambda section: int(section["index"]))

    def _html_to_summary(self, html: str) -> str:
        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")
        for tag_name in ("style", "script", "table", "sup", "figure", "ol", "ul", "dl"):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        paragraphs: list[str] = []
        for paragraph in soup.find_all("p"):
            text = self._clean_text(paragraph.get_text(" ", strip=True))
            if text:
                paragraphs.append(text)
            if len(paragraphs) >= 2:
                break

        summary = " ".join(paragraphs)
        if len(summary) > 900:
            summary = summary[:897].rsplit(" ", 1)[0] + "..."
        return summary

    def _extract_infobox_facts(self, html: str) -> dict[str, str]:
        if not html:
            return {}

        soup = BeautifulSoup(html, "lxml")
        infobox = soup.select_one("table.infobox")
        if infobox is None:
            return {}

        facts: dict[str, str] = {}
        for row in infobox.find_all("tr"):
            heading = row.find("th")
            value_cell = row.find("td")
            if heading is None or value_cell is None:
                continue

            raw_label = self._clean_text(heading.get_text(" ", strip=True))
            if not raw_label:
                continue
            label = self._normalize_infobox_label(raw_label)
            if label is None or label in facts:
                continue

            value = self._clean_text(value_cell.get_text(" ", strip=True))
            value = re.sub(r"\s*\[\d+\]\s*", " ", value)
            value = re.sub(r"\s+", " ", value).strip(" ,;")
            if not value:
                continue
            if len(value) > 180:
                value = value[:177].rsplit(" ", 1)[0] + "..."
            facts[label] = value
        return facts

    def _claim_values(
        self,
        claims: list[dict[str, Any]],
        label_lookup: dict[str, str],
    ) -> list[str]:
        values: list[str] = []
        for claim in claims:
            datavalue = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if datavalue is None:
                continue
            if isinstance(datavalue, dict) and datavalue.get("id"):
                label = label_lookup.get(datavalue["id"])
                if label:
                    values.append(label)
                continue
            if isinstance(datavalue, dict) and datavalue.get("time"):
                formatted = self._format_wikidata_time(datavalue["time"])
                if formatted:
                    values.append(formatted)
                continue
            if isinstance(datavalue, str):
                values.append(datavalue)

        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _claim_entity_id(self, claim: dict[str, Any]) -> str | None:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict):
            return value.get("id")
        return None

    def _format_wikidata_time(self, raw_time: str) -> str | None:
        match = re.match(r"^[+-](\d{4})-(\d{2})-(\d{2})T", raw_time)
        if not match:
            return None
        year, month, day = match.groups()
        if month == "00":
            return year
        if day == "00":
            return f"{year}-{month}"
        return f"{year}-{month}-{day}"

    def _candidate_titles(self, make: str, model: str, year: int | None) -> list[str]:
        base = f"{make} {model}".strip()
        candidates = [
            base,
            f"{base} automobile",
            f"{base} car",
        ]
        if year is not None:
            candidates.insert(0, f"{year} {base}")

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _is_relevant_page(self, page: dict[str, Any], make: str, model: str) -> bool:
        haystack = self._normalize_relevance_text(
            " ".join(
                part
                for part in (
                    page.get("title"),
                    page.get("summary"),
                )
                if part
            )
        )
        if not haystack:
            return False

        make_tokens = self._relevance_tokens(make)
        model_tokens = self._relevance_tokens(model)
        if make_tokens and not any(token in haystack for token in make_tokens):
            return False
        return not model_tokens or any(token in haystack for token in model_tokens)

    def _relevance_tokens(self, value: str) -> list[str]:
        tokens = []
        for token in re.findall(r"[A-Za-z0-9]+", value.casefold()):
            if len(token) > 2 or any(char.isdigit() for char in token):
                tokens.append(token)
        return tokens

    def _normalize_relevance_text(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    def _cache_path(self, make: str, model: str) -> Path:
        slug = f"{self._slug(make)}__{self._slug(model)}.json"
        return self.settings.reference_cache_path / "wikimedia" / slug

    def _miss_cache_path(self, make: str, model: str) -> Path:
        slug = f"{self._slug(make)}__{self._slug(model)}.json"
        return self.settings.reference_cache_path / "wikimedia_miss" / slug

    def _load_cache(self, path: Path, *, allow_stale: bool = False) -> ReferenceProfile | None:
        if not path.exists():
            return None
        expires_after = timedelta(hours=self.settings.reference_cache_ttl_hours)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if not allow_stale and datetime.now(UTC) - modified_at > expires_after:
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("cache_version") != _CACHE_VERSION:
                return None
            return ReferenceProfile(
                provider=payload["provider"],
                title=payload["title"],
                canonical_url=payload.get("canonical_url"),
                image_url=payload.get("image_url"),
                summary=payload.get("summary"),
                facts=payload.get("facts", {}),
                sections=[ReferenceSection(**section) for section in payload.get("sections", [])],
                sources=[ReferenceSource(**source) for source in payload.get("sources", [])],
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.logger.warning("Failed to read Wikimedia cache %s: %s", path, exc)
            return None

    def _load_miss_cache(self, path: Path) -> bool:
        if not path.exists():
            return False
        expires_after = timedelta(hours=self.settings.reference_miss_cache_ttl_hours)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if datetime.now(UTC) - modified_at > expires_after:
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.logger.warning("Failed to read Wikimedia miss cache %s: %s", path, exc)
            return False
        return payload.get("cache_version") == _CACHE_VERSION and payload.get("miss") is True

    def _write_miss_cache(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = {
                "cache_version": _CACHE_VERSION,
                "miss": True,
                "provider": self.provider_name,
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            self.logger.warning("Failed to write Wikimedia miss cache %s: %s", path, exc)

    def _clear_miss_cache(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            self.logger.warning("Failed to clear Wikimedia miss cache %s: %s", path, exc)

    def _coerce_part(
        self,
        result: T | Exception,
        *,
        default: T,
        label: str,
        page_title: str,
    ) -> T:
        if isinstance(result, Exception):
            self.logger.warning(
                "Failed to fetch Wikimedia %s for %s: %s",
                label,
                page_title,
                result,
            )
            return default
        return result

    def _write_cache(self, path: Path, profile: ReferenceProfile) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = {"cache_version": _CACHE_VERSION, **asdict(profile)}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            self.logger.warning("Failed to write Wikimedia cache %s: %s", path, exc)

    def _clean_text(self, text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _normalize_infobox_label(self, label: str) -> str | None:
        normalized = re.sub(r"[^a-z0-9]+", " ", label.casefold()).strip()
        return _INFOBOX_FACT_ALIASES.get(normalized)

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "unknown"
