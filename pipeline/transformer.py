from __future__ import annotations

import hashlib
import re
import unicodedata


class ContentTransformer:
    _WHITESPACE = re.compile(r"\s+")
    _NON_PRINTABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    def clean_text(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = self._NON_PRINTABLE.sub("", text)
        text = self._WHITESPACE.sub(" ", text)
        return text.strip()

    def normalize_url(self, url: str) -> str:
        url = url.strip()
        url = re.sub(r"#.*$", "", url)
        url = re.sub(r"/+", "/", url)
        return url

    def compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def truncate_text(self, text: str, max_length: int = 1000) -> str:
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def normalize_whitespace(self, text: str) -> str:
        return self._WHITESPACE.sub(" ", text).strip()

    def strip_html(self, text: str) -> str:
        return re.sub(r"<[^>]+>", "", text)

    def extract_sentences(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def compute_readability_score(self, text: str) -> float:
        words = text.split()
        if not words:
            return 0.0
        sentences = self.extract_sentences(text)
        avg_word_length = sum(len(w) for w in words) / len(words)
        avg_sentence_length = len(words) / max(len(sentences), 1)
        score = 100.0
        score -= max(0, avg_sentence_length - 15) * 2
        score -= max(0, avg_word_length - 5) * 10
        return max(0.0, min(100.0, score))
