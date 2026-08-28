from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import httpx

@dataclass
class PageInfo:
    page_number: int
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    filename: Optional[str] = None

@dataclass
class ChapterInfo:
    id: str
    chapter_number: float
    chapter_display: str
    title: str = ""
    volume: Optional[str] = None
    language: str = "en"
    scanlation_group: str = ""
    publish_date: Optional[str] = None
    url: str = ""
    page_count: Optional[int] = None
    source_name: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MangaInfo:
    id: str
    title: str
    url: str
    source_name: str
    cover_url: str = ""
    synopsis: str = ""
    author: str = ""
    artist: str = ""
    status: str = ""
    genres: List[str] = field(default_factory=list)
    available_languages: List[str] = field(default_factory=list)
    chapters: List[ChapterInfo] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

class BaseScraper(ABC):
    name: str = "base"
    
    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def create_client(self, extra_headers: Optional[Dict[str, str]] = None) -> httpx.AsyncClient:
        h = dict(self.headers)
        if extra_headers:
            h.update(extra_headers)
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers=h,
            follow_redirects=True,
            verify=False # Bypass SSL certificate mismatch on manga mirror domains
        )

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this scraper can handle the given URL."""
        pass

    @abstractmethod
    async def get_manga_info(self, url: str, language: str = "en") -> MangaInfo:
        """Fetch manga metadata and chapter list."""
        pass

    @abstractmethod
    async def get_chapter_pages(self, chapter: ChapterInfo) -> List[PageInfo]:
        """Fetch page URLs for a specific chapter."""
        pass

    async def search(self, query: str, limit: int = 10) -> List[MangaInfo]:
        """Search manga by query string if supported."""
        return []
