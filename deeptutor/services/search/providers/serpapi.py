"""
SerpAPI Provider — https://serpapi.com

Supports two modes:
- ``mode="search"`` (default) → ``engine=google`` organic web results
- ``mode="images"``           → ``engine=google_images`` image results

Returns a standardized ``WebSearchResponse``. For image mode, citations carry
``type="image"`` and ``attributes`` with ``thumbnail`` / ``original`` URLs so
the frontend can render a thumbnail gallery without re-fetching.

Environment:
- ``SERPAPI_API_KEY``  (preferred)
- ``SEARCH_API_KEY``   (fallback if SerpAPI is the active provider)
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from urllib.parse import urlparse

import requests

from ..base import BaseSearchProvider
from ..types import Citation, SearchResult, WebSearchResponse
from . import register_provider


class SerpAPIError(Exception):
    """SerpAPI error"""


@register_provider("serpapi")
class SerpAPIProvider(BaseSearchProvider):
    """SerpAPI — google search + google_images modes."""

    display_name = "SerpAPI"
    description = "Google SERP / image results via SerpAPI"
    supports_answer = False  # Raw SERP — auto-consolidated by AnswerConsolidator
    BASE_URL = "https://serpapi.com/search"
    # Accept both ``SERPAPI_API_KEY`` (canonical) and ``SERP_API_KEY`` (a
    # common alias users paste from informal docs); fall back to the
    # unified ``SEARCH_API_KEY`` last.
    API_KEY_ENV_VARS = ("SERPAPI_API_KEY", "SERP_API_KEY", "SEARCH_API_KEY")

    def search(
        self,
        query: str,
        mode: str = "search",
        num: int = 10,
        gl: str = "us",
        hl: str = "en",
        timeout: int = 30,
        **kwargs: Any,
    ) -> WebSearchResponse:
        engine = "google_images" if mode == "images" else "google"
        params: dict[str, Any] = {
            "engine": engine,
            "q": query,
            "api_key": self.api_key,
            "num": num,
            "gl": gl,
            "hl": hl,
            "no_cache": "false",
        }
        # Allow caller-supplied extras (e.g. ``location``, ``ijn`` for image pagination).
        for key in ("location", "ijn", "tbs", "google_domain", "device"):
            if kwargs.get(key) is not None:
                params[key] = kwargs[key]

        self.logger.debug(f"Calling SerpAPI engine={engine}, num={num}")
        response = requests.get(self.BASE_URL, params=params, timeout=timeout)

        if response.status_code != 200:
            try:
                err = response.json()
            except (json.JSONDecodeError, ValueError):
                err = {"error": response.text}
            raise SerpAPIError(
                f"SerpAPI error: {response.status_code} - {err.get('error', err)}"
            )

        data = response.json()
        if mode == "images":
            return self._parse_images(query, data)
        return self._parse_search(query, data)

    @staticmethod
    def _domain(url: str) -> str:
        try:
            host = urlparse(url).netloc
            return host[4:] if host.startswith("www.") else host
        except Exception:
            return ""

    def _parse_search(self, query: str, data: dict[str, Any]) -> WebSearchResponse:
        organic = data.get("organic_results") or []
        citations: list[Citation] = []
        results: list[SearchResult] = []

        for i, r in enumerate(organic, start=1):
            title = r.get("title", "")
            url_val = r.get("link", "")
            snippet = r.get("snippet", "")
            date = r.get("date", "")
            source = r.get("source") or self._domain(url_val)

            results.append(
                SearchResult(
                    title=title,
                    url=url_val,
                    snippet=snippet,
                    date=date,
                    source=source,
                )
            )
            citations.append(
                Citation(
                    id=i,
                    reference=f"[{i}]",
                    url=url_val,
                    title=title,
                    snippet=snippet,
                    date=date,
                    source=source,
                )
            )

        metadata: dict[str, Any] = {"finish_reason": "stop", "engine": "google"}
        if data.get("answer_box"):
            metadata["answerBox"] = data["answer_box"]
        if data.get("knowledge_graph"):
            metadata["knowledgeGraph"] = data["knowledge_graph"]
        if data.get("related_questions"):
            metadata["peopleAlsoAsk"] = data["related_questions"]

        # Free image previews from inline_images / related image carousels.
        inline_images = data.get("inline_images") or []
        if inline_images:
            metadata["images"] = [
                {
                    "thumbnail": img.get("thumbnail") or img.get("original") or "",
                    "original": img.get("original") or img.get("thumbnail") or "",
                    "title": img.get("title", ""),
                    "link": img.get("link", "") or img.get("source", ""),
                    "source": img.get("source", ""),
                    "position": img.get("position", idx),
                }
                for idx, img in enumerate(inline_images, start=1)
                if img.get("thumbnail") or img.get("original")
            ]

        answer = ""
        if data.get("answer_box"):
            ab = data["answer_box"]
            answer = ab.get("answer") or ab.get("snippet") or ""
        elif data.get("knowledge_graph"):
            answer = data["knowledge_graph"].get("description", "")

        return WebSearchResponse(
            query=query,
            answer=answer,
            provider="serpapi",
            timestamp=datetime.now().isoformat(),
            model="serpapi-google",
            citations=citations,
            search_results=results,
            usage={},
            metadata=metadata,
        )

    def _parse_images(self, query: str, data: dict[str, Any]) -> WebSearchResponse:
        images = data.get("images_results") or []
        citations: list[Citation] = []
        results: list[SearchResult] = []
        gallery: list[dict[str, Any]] = []

        for i, img in enumerate(images, start=1):
            thumb = img.get("thumbnail") or ""
            original = img.get("original") or thumb
            title = img.get("title", "")
            link = img.get("link", "") or img.get("source", "")
            source = img.get("source") or self._domain(link)

            if not (thumb or original):
                continue

            entry = {
                "thumbnail": thumb,
                "original": original,
                "title": title,
                "link": link,
                "source": source,
                "position": img.get("position", i),
            }
            gallery.append(entry)

            results.append(
                SearchResult(
                    title=title,
                    url=link or original,
                    snippet=source,
                    source=source,
                    attributes=entry,
                )
            )
            citations.append(
                Citation(
                    id=i,
                    reference=f"[{i}]",
                    url=link or original,
                    title=title,
                    snippet=source,
                    source=source,
                    type="image",
                    icon=thumb,
                )
            )

        metadata: dict[str, Any] = {
            "finish_reason": "stop",
            "engine": "google_images",
            "images": gallery,
        }
        return WebSearchResponse(
            query=query,
            answer="",
            provider="serpapi_images",
            timestamp=datetime.now().isoformat(),
            model="serpapi-google_images",
            citations=citations,
            search_results=results,
            usage={},
            metadata=metadata,
        )
