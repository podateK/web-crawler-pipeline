from __future__ import annotations

import hashlib
import math
import re
from urllib.parse import (
    parse_qs,
    urlparse,
    urldefrag,
    urljoin,
    urlencode,
    urlunparse,
)


DENY_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".wmv", ".flv", ".mov", ".mkv", ".wav",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz", ".bz2", ".7z",
    ".css", ".js", ".xml", ".json",
    ".exe", ".dll", ".so", ".dylib",
})

_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid",
})


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    try:
        if base_url:
            url = urljoin(base_url, url)
        url, _ = urldefrag(url)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None
        path = re.sub(r"/+", "/", parsed.path)
        path = path.rstrip("/") or "/"
        params = parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(filtered, doseq=True) if filtered else ""
        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            query,
            "",
        ))
    except Exception:
        return None


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def has_denied_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DENY_EXTENSIONS)


def is_same_domain(url: str, domain: str) -> bool:
    return extract_domain(url) == domain


class URLBloomFilter:
    def __init__(self, expected_items: int = 100_000, fp_rate: float = 0.001):
        self._size = self._optimal_size(expected_items, fp_rate)
        self._hash_count = self._optimal_hash_count(self._size, expected_items)
        self._bit_array = bytearray(self._size // 8 + 1)
        self._count = 0

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        return max(int(math.ceil(m)), 64)

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        k = (m / n) * math.log(2)
        return max(int(math.ceil(k)), 1)

    def _hashes(self, item: str) -> list[int]:
        data = item.encode("utf-8")
        positions = []
        for i in range(self._hash_count):
            h = hashlib.sha256(data + i.to_bytes(4, "big")).digest()
            positions.append(int.from_bytes(h[:4], "big") % self._size)
        return positions

    def add(self, item: str) -> bool:
        is_new = item not in self
        if is_new:
            for pos in self._hashes(item):
                self._bit_array[pos // 8] |= 1 << (pos % 8)
            self._count += 1
        return is_new

    def __contains__(self, item: str) -> bool:
        return all(
            self._bit_array[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )

    @property
    def count(self) -> int:
        return self._count
