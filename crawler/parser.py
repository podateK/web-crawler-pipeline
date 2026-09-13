from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from utils.url_utils import normalize_url

logger = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    url: str
    title: str
    description: str
    text: str
    links: list[str] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    headings: dict[str, list[str]] = field(default_factory=dict)
    html: str = ""
    word_count: int = 0


class HTMLParser:
    def __init__(self) -> None:
        self._parser = "lxml"

    def parse(self, url: str, html: str) -> ParsedPage:
        soup = BeautifulSoup(html, self._parser)

        title = self._extract_title(soup)
        description = self._extract_description(soup)
        meta = self._extract_meta(soup)
        headings = self._extract_headings(soup)
        links = self._extract_links(soup, url)
        text = soup.get_text(separator=" ", strip=True)
        word_count = len(text.split()) if text else 0

        return ParsedPage(
            url=url,
            title=title,
            description=description,
            text=text,
            links=links,
            meta=meta,
            headings=headings,
            html=html,
            word_count=word_count,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        tag = soup.find("title")
        return tag.get_text(strip=True) if tag else ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            return tag["content"]
        tag = soup.find("meta", attrs={"property": "og:description"})
        if tag and tag.get("content"):
            return tag["content"]
        return ""

    def _extract_meta(self, soup: BeautifulSoup) -> dict[str, str]:
        meta: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property") or tag.get("http-equiv")
            content = tag.get("content")
            if name and content:
                meta[name] = content
        return meta

    def _extract_headings(self, soup: BeautifulSoup) -> dict[str, list[str]]:
        headings: dict[str, list[str]] = {}
        for level in range(1, 7):
            tag_name = f"h{level}"
            found = soup.find_all(tag_name)
            if found:
                headings[tag_name] = [h.get_text(strip=True) for h in found]
        return headings

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            normalized = normalize_url(href, base_url)
            if normalized and normalized not in seen:
                seen.add(normalized)
                links.append(normalized)
        return links
