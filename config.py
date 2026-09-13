from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CrawlerConfig:
    start_urls: list[str] = field(default_factory=list)
    max_concurrency: int = 10
    max_depth: int = 3
    max_pages: int = 1000
    request_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    rate_limit_per_second: float = 1.0
    respect_robots_txt: bool = True
    rotate_user_agent: bool = True
    db_path: Path = Path("crawl_data.db")
    log_level: str = "INFO"
    allowed_schemes: tuple[str, ...] = ("http", "https")
    deny_extensions: frozenset[str] = field(default_factory=lambda: frozenset({
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp",
        ".mp3", ".mp4", ".avi", ".wmv", ".flv", ".mov", ".mkv", ".wav",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".tar", ".gz", ".bz2", ".7z",
        ".css", ".js", ".xml", ".json",
        ".exe", ".dll", ".so", ".dylib",
    }))
    bloom_filter_size: int = 1 << 20

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"
