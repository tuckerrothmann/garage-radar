import os
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from garage_radar.reference_sources.wikimedia import WikimediaVehicleProfileProvider


class TestWikimediaVehicleProfileProvider:
    async def test_fetch_profile_builds_sections_and_facts(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path

        async def fake_request_json(client, url, params):
            if url.endswith("/w/api.php") and params["action"] == "query":
                return {
                    "query": {
                        "pages": [
                            {
                                "title": "BMW M3",
                                "extract": "The BMW M3 is a high-performance version of the BMW 3 Series.",
                                "fullurl": "https://en.wikipedia.org/wiki/BMW_M3",
                                "thumbnail": {"source": "https://upload.wikimedia.org/example.jpg"},
                                "pageprops": {"wikibase_item": "Q796579"},
                            }
                        ]
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and params.get("section") == 0:
                return {
                    "parse": {
                        "text": {
                            "*": """
                            <table class="infobox">
                              <tr><th>Manufacturer</th><td>BMW M GmbH</td></tr>
                              <tr><th>Class</th><td>Sports car / compact executive car</td></tr>
                              <tr><th>Body style</th><td>Coupe, sedan, convertible</td></tr>
                            </table>
                            """
                        }
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "tocdata":
                return {
                    "parse": {
                        "tocdata": {
                            "sections": [
                                {"tocLevel": 1, "index": "1", "line": "History", "anchor": "History"},
                                {"tocLevel": 1, "index": "2", "line": "Motorsport", "anchor": "Motorsport"},
                                {"tocLevel": 1, "index": "3", "line": "References", "anchor": "References"},
                            ]
                        }
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and str(params.get("section")) == "1":
                return {
                    "parse": {
                        "text": {
                            "*": "<div><p>History paragraph one.</p><p>History paragraph two.</p></div>"
                        }
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and str(params.get("section")) == "2":
                return {
                    "parse": {
                        "text": {
                            "*": "<div><p>Motorsport paragraph one.</p><p>Motorsport paragraph two.</p></div>"
                        }
                    }
                }
            if params["action"] == "wbgetentities" and params["ids"] == "Q796579":
                return {
                    "entities": {
                        "Q796579": {
                            "descriptions": {"en": {"value": "car model"}},
                            "claims": {
                                "P176": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {"value": {"id": "Q26678"}}
                                        }
                                    }
                                ],
                                "P495": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {"value": {"id": "Q183"}}
                                        }
                                    }
                                ],
                                "P571": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"time": "+1986-01-01T00:00:00Z"}
                                            }
                                        }
                                    }
                                ],
                            },
                        }
                    }
                }
            if params["action"] == "wbgetentities" and params["ids"] == "Q183|Q26678":
                return {
                    "entities": {
                        "Q183": {"labels": {"en": {"value": "Germany"}}},
                        "Q26678": {"labels": {"en": {"value": "BMW"}}},
                    }
                }
            raise AssertionError(f"Unexpected request: {url} {params}")

        provider._request_json = AsyncMock(side_effect=fake_request_json)

        profile = await provider.fetch_profile("BMW", "M3", year=1988)

        assert profile is not None
        assert profile.title == "BMW M3"
        assert profile.summary == "The BMW M3 is a high-performance version of the BMW 3 Series."
        assert profile.canonical_url == "https://en.wikipedia.org/wiki/BMW_M3"
        assert profile.image_url == "https://upload.wikimedia.org/example.jpg"
        assert profile.facts["Manufacturer"] == "BMW M GmbH"
        assert profile.facts["Vehicle class"] == "Sports car / compact executive car"
        assert profile.facts["Body style"] == "Coupe, sedan, convertible"
        assert profile.facts["Country of origin"] == "Germany"
        assert profile.facts["Introduced"] == "1986-01-01"
        assert len(profile.sections) == 2
        assert profile.sections[0].title == "History"
        assert "History paragraph one." in profile.sections[0].summary
        assert profile.sources[0].name == "Wikipedia"

    def test_extract_infobox_facts(self):
        provider = WikimediaVehicleProfileProvider()

        facts = provider._extract_infobox_facts(
            """
            <table class="infobox">
              <tr><th>Production</th><td>1966-present</td></tr>
              <tr><th>Layout</th><td>Front-engine, four-wheel drive</td></tr>
              <tr><th>Random field</th><td>Ignore me</td></tr>
            </table>
            """
        )

        assert facts == {
            "Production": "1966-present",
            "Layout": "Front-engine, four-wheel drive",
        }

    async def test_fetch_profile_uses_fresh_cache(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path
        cache_dir = tmp_path / "wikimedia"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "ford__bronco.json"
        cache_file.write_text(
            """
            {
              "cache_version": 3,
              "provider": "Wikimedia",
              "title": "Ford Bronco",
              "canonical_url": "https://en.wikipedia.org/wiki/Ford_Bronco",
              "image_url": null,
              "summary": "Cached summary",
              "facts": {"Manufacturer": "Ford"},
              "sections": [],
              "sources": [{"name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Ford_Bronco", "license": "CC BY-SA 4.0"}]
            }
            """.strip(),
            encoding="utf-8",
        )

        provider._request_json = AsyncMock()
        profile = await provider.fetch_profile("Ford", "Bronco")

        assert profile is not None
        assert profile.title == "Ford Bronco"
        assert profile.summary == "Cached summary"
        provider._request_json.assert_not_called()

    async def test_fetch_profile_returns_none_on_http_error(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path
        provider._request_json = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Forbidden",
                request=httpx.Request("GET", "https://en.wikipedia.org/w/api.php"),
                response=httpx.Response(403),
            )
        )

        profile = await provider.fetch_profile("BMW", "M3")

        assert profile is None

    async def test_fetch_profile_handles_missing_tocdata(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path

        async def fake_request_json(client, url, params):
            if url.endswith("/w/api.php") and params["action"] == "query":
                return {
                    "query": {
                        "pages": [
                            {
                                "title": "Chevrolet Corvette",
                                "extract": "The Chevrolet Corvette is a line of sports cars.",
                                "fullurl": "https://en.wikipedia.org/wiki/Chevrolet_Corvette",
                                "pageprops": {"wikibase_item": "Q1126262"},
                            }
                        ]
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and params.get("section") == 0:
                return {"parse": {"text": {"*": "<table class='infobox'></table>"}}}
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "tocdata":
                return {"parse": {"tocdata": None}}
            if params["action"] == "wbgetentities" and params["ids"] == "Q1126262":
                return {
                    "entities": {
                        "Q1126262": {
                            "descriptions": {"en": {"value": "sports car"}},
                            "claims": {},
                        }
                    }
                }
            raise AssertionError(f"Unexpected request: {url} {params}")

        provider._request_json = AsyncMock(side_effect=fake_request_json)

        profile = await provider.fetch_profile("Chevrolet", "Corvette Z06", year=2002)

        assert profile is not None
        assert profile.title == "Chevrolet Corvette"
        assert profile.sections == []

    async def test_fetch_profile_returns_partial_profile_when_sections_fail(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path

        async def fake_request_json(client, url, params):
            if url.endswith("/w/api.php") and params["action"] == "query":
                return {
                    "query": {
                        "pages": [
                            {
                                "title": "BMW 5 Series",
                                "extract": "The BMW 5 Series is an executive car manufactured by BMW.",
                                "fullurl": "https://en.wikipedia.org/wiki/BMW_5_Series",
                                "pageprops": {"wikibase_item": "Q153804"},
                            }
                        ]
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and params.get("section") == 0:
                return {
                    "parse": {
                        "text": {
                            "*": "<table class='infobox'><tr><th>Manufacturer</th><td>BMW</td></tr></table>"
                        }
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "tocdata":
                return {
                    "parse": {
                        "tocdata": {
                            "sections": [
                                {"tocLevel": 1, "index": "1", "line": "History", "anchor": "History"},
                            ]
                        }
                    }
                }
            if url.endswith("/w/api.php") and params["action"] == "parse" and params["prop"] == "text" and str(params.get("section")) == "1":
                raise httpx.ReadTimeout("section timeout")
            if params["action"] == "wbgetentities" and params["ids"] == "Q153804":
                return {
                    "entities": {
                        "Q153804": {
                            "descriptions": {"en": {"value": "executive car"}},
                            "claims": {},
                        }
                    }
                }
            raise AssertionError(f"Unexpected request: {url} {params}")

        provider._request_json = AsyncMock(side_effect=fake_request_json)

        profile = await provider.fetch_profile("BMW", "5-Series")

        assert profile is not None
        assert profile.title == "BMW 5 Series"
        assert profile.facts["Manufacturer"] == "BMW"
        assert profile.sections == []

    async def test_fetch_profile_uses_stale_cache_on_timeout(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path
        provider.settings.reference_cache_ttl_hours = 1
        cache_dir = tmp_path / "wikimedia"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bmw__530i.json"
        cache_file.write_text(
            """
            {
              "cache_version": 3,
              "provider": "Wikimedia",
              "title": "BMW 5 Series",
              "canonical_url": "https://en.wikipedia.org/wiki/BMW_5_Series",
              "image_url": null,
              "summary": "Stale cached summary",
              "facts": {"Manufacturer": "BMW"},
              "sections": [],
              "sources": [{"name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/BMW_5_Series", "license": "CC BY-SA 4.0"}]
            }
            """.strip(),
            encoding="utf-8",
        )
        stale_mtime = cache_file.stat().st_mtime - 7200
        os.utime(cache_file, (stale_mtime, stale_mtime))

        provider._request_json = AsyncMock(side_effect=TimeoutError("timed out"))

        profile = await provider.fetch_profile("BMW", "530i")

        assert profile is not None
        assert profile.title == "BMW 5 Series"
        assert profile.summary == "Stale cached summary"

    async def test_fetch_profile_uses_recent_miss_cache(self, tmp_path: Path):
        provider = WikimediaVehicleProfileProvider()
        provider.settings.reference_cache_path = tmp_path
        miss_dir = tmp_path / "wikimedia_miss"
        miss_dir.mkdir(parents=True, exist_ok=True)
        miss_file = miss_dir / "bmw__530i.json"
        miss_file.write_text(
            """
            {
              "cache_version": 3,
              "miss": true,
              "provider": "Wikimedia"
            }
            """.strip(),
            encoding="utf-8",
        )

        provider._request_json = AsyncMock()

        profile = await provider.fetch_profile("BMW", "530i")

        assert profile is None
        provider._request_json.assert_not_called()

    async def test_resolve_page_skips_irrelevant_result(self):
        provider = WikimediaVehicleProfileProvider()
        provider._candidate_titles = lambda make, model, year: ["Ford Mustang Shelby GT350"]
        provider._search_titles = AsyncMock(return_value=["Ford Mustang"])
        provider._fetch_page_summary = AsyncMock(
            side_effect=[
                {
                    "title": "Automobile (magazine)",
                    "summary": "Automobile was an American automobile magazine.",
                },
                {
                    "title": "Ford Mustang",
                    "summary": "The Ford Mustang is a series of American automobiles manufactured by Ford.",
                },
            ]
        )

        page = await provider._resolve_page(AsyncMock(), "Ford", "Mustang Shelby GT350", 2017)

        assert page is not None
        assert page["title"] == "Ford Mustang"

    def test_choose_sections_prioritizes_relevant_topics_and_limits_count(self):
        provider = WikimediaVehicleProfileProvider()

        sections = provider._choose_sections(
            [
                {"tocLevel": 1, "index": "1", "line": "Overview", "anchor": "Overview"},
                {"tocLevel": 1, "index": "2", "line": "History", "anchor": "History"},
                {"tocLevel": 1, "index": "3", "line": "Design", "anchor": "Design"},
                {"tocLevel": 1, "index": "4", "line": "Technology", "anchor": "Technology"},
                {"tocLevel": 1, "index": "5", "line": "Motorsport", "anchor": "Motorsport"},
                {"tocLevel": 1, "index": "6", "line": "Reception", "anchor": "Reception"},
                {"tocLevel": 1, "index": "7", "line": "Legacy", "anchor": "Legacy"},
                {"tocLevel": 1, "index": "8", "line": "References", "anchor": "References"},
            ]
        )

        assert len(sections) == 6
        assert [section["line"] for section in sections] == [
            "History",
            "Design",
            "Technology",
            "Motorsport",
            "Reception",
            "Legacy",
        ]
