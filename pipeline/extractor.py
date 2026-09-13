from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class ExtractedData:
    tables: list[list[list[str]]] = field(default_factory=list)
    lists: list[list[str]] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    emails: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)


class DataExtractor:
    def __init__(self) -> None:
        self._parser = "lxml"

    def extract(self, html: str, url: str = "") -> ExtractedData:
        soup = BeautifulSoup(html, self._parser)
        return ExtractedData(
            tables=self._extract_tables(soup),
            lists=self._extract_lists(soup),
            metadata=self._extract_metadata(soup, url),
            emails=self._extract_emails(soup),
            phone_numbers=self._extract_phones(soup),
        )

    def _extract_tables(self, soup: BeautifulSoup) -> list[list[list[str]]]:
        tables: list[list[list[str]]] = []
        for table in soup.find_all("table"):
            rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def _extract_lists(self, soup: BeautifulSoup) -> list[list[str]]:
        lists: list[list[str]] = []
        for ul in soup.find_all(["ul", "ol"]):
            items = [li.get_text(strip=True) for li in ul.find_all("li", recursive=False)]
            if items:
                lists.append(items)
        return lists

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> dict[str, str]:
        metadata: dict[str, str] = {"source_url": url}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property") or tag.get("http-equiv")
            content = tag.get("content")
            if name and content:
                metadata[name] = content
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)
        for tag in soup.find_all("link", rel="canonical"):
            href = tag.get("href")
            if href:
                metadata["canonical"] = href
        return metadata

    def _extract_emails(self, soup: BeautifulSoup) -> list[str]:
        text = soup.get_text()
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = list(set(re.findall(pattern, text)))
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip()
                if email and email not in emails:
                    emails.append(email)
        return sorted(emails)

    def _extract_phones(self, soup: BeautifulSoup) -> list[str]:
        text = soup.get_text()
        pattern = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
        phones = list(set(re.findall(pattern, text)))
        return sorted(phones[:20])

    @staticmethod
    def to_json(data: ExtractedData) -> str:
        return json.dumps({
            "tables": data.tables,
            "lists": data.lists,
            "metadata": data.metadata,
            "emails": data.emails,
            "phone_numbers": data.phone_numbers,
        }, ensure_ascii=False, default=str)

    @staticmethod
    def from_json(json_str: str) -> ExtractedData:
        return ExtractedData(**json.loads(json_str))
