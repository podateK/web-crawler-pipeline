from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from utils.url_utils import extract_domain


@dataclass
class AnalyticsResult:
    url: str
    title: str
    word_count: int
    char_count: int
    sentence_count: int
    avg_word_length: float
    avg_sentence_length: float
    top_words: list[tuple[str, int]]
    link_count: int
    internal_links: int
    external_links: int
    unique_domains: list[str]
    heading_counts: dict[str, int]
    readability_score: float
    content_density: float
    images: int
    scripts: int
    stylesheets: int

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "sentence_count": self.sentence_count,
            "avg_word_length": round(self.avg_word_length, 2),
            "avg_sentence_length": round(self.avg_sentence_length, 2),
            "top_words": self.top_words[:20],
            "link_count": self.link_count,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "unique_domains": self.unique_domains[:20],
            "heading_counts": self.heading_counts,
            "readability_score": round(self.readability_score, 2),
            "content_density": round(self.content_density, 2),
            "images": self.images,
            "scripts": self.scripts,
            "stylesheets": self.stylesheets,
        }


class ContentAnalyzer:
    _STOP_WORDS: frozenset[str] = frozenset({
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need", "dare",
        "ought", "used", "this", "that", "these", "those", "i", "me", "my",
        "we", "our", "you", "your", "he", "him", "his", "she", "her", "it",
        "its", "they", "them", "their", "what", "which", "who", "whom",
        "where", "when", "why", "how", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "no", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "because", "as",
        "until", "while", "about", "between", "through", "during", "before",
        "after", "above", "below", "up", "down", "out", "off", "over",
        "under", "again", "further", "then", "once", "here", "there",
        "also", "into", "if", "any", "many", "much", "well", "back",
        "even", "still", "new", "like", "using", "used", "first",
        "get", "make", "go", "see", "come", "know", "take", "think",
    })

    def analyze(
        self,
        url: str,
        text: str,
        html: str,
        title: str = "",
        links: list[str] | None = None,
    ) -> AnalyticsResult:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml") if html else None

        words = text.split() if text else []
        words_lower = [w.lower() for w in words if len(w) > 1]

        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]

        filtered = [w for w in words_lower if w not in self._STOP_WORDS and w.isalpha()]
        top_words = Counter(filtered).most_common(20)

        base_domain = extract_domain(url) if url else ""
        internal = 0
        external = 0
        domains: set[str] = set()

        for link in (links or []):
            link_domain = extract_domain(link)
            domains.add(link_domain)
            if link_domain == base_domain:
                internal += 1
            else:
                external += 1

        heading_counts: dict[str, int] = {}
        images = 0
        scripts = 0
        styles = 0
        if soup:
            for level in range(1, 7):
                count = len(soup.find_all(f"h{level}"))
                if count:
                    heading_counts[f"h{level}"] = count
            images = len(soup.find_all("img"))
            scripts = len(soup.find_all("script"))
            styles = len(soup.find_all("link", rel="stylesheet")) + len(soup.find_all("style"))

        total_html = len(html) if html else 0
        total_text = len(text) if text else 0
        content_density = (total_text / total_html * 100) if total_html > 0 else 0.0

        readability = self._flesch_kincaid(words, sentences)

        return AnalyticsResult(
            url=url,
            title=title,
            word_count=len(words),
            char_count=total_text,
            sentence_count=len(sentences),
            avg_word_length=sum(len(w) for w in words) / max(len(words), 1),
            avg_sentence_length=len(words) / max(len(sentences), 1),
            top_words=top_words,
            link_count=len(links or []),
            internal_links=internal,
            external_links=external,
            unique_domains=sorted(domains),
            heading_counts=heading_counts,
            readability_score=readability,
            content_density=content_density,
            images=images,
            scripts=scripts,
            stylesheets=styles,
        )

    def _flesch_kincaid(self, words: list[str], sentences: list[str]) -> float:
        if not words or not sentences:
            return 0.0
        syllables = sum(self._count_syllables(w) for w in words)
        w = len(words)
        s = len(sentences)
        score = 206.835 - 1.015 * (w / s) - 84.6 * (syllables / w)
        return max(0.0, min(100.0, score))

    @staticmethod
    def _count_syllables(word: str) -> int:
        word = word.lower().strip()
        if len(word) <= 3:
            return 1
        vowels = "aeiouy"
        count = 0
        prev_vowel = False
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        if word.endswith("e") and count > 1:
            count -= 1
        return max(count, 1)
