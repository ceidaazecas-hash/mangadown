from typing import List, Optional
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo
from .mangadex import MangaDexScraper
from .atsumaru import AtsumaruScraper
from .manganato import ManganatoScraper
from .mangafreak import MangaFreakScraper
from .generic import GenericScraper

ALL_SCRAPERS: List[BaseScraper] = [
    MangaDexScraper(),
    AtsumaruScraper(),
    ManganatoScraper(),
    MangaFreakScraper(),
    GenericScraper(),
]

def get_scraper_for_url(url: str) -> BaseScraper:
    for scraper in ALL_SCRAPERS:
        if scraper.can_handle(url):
            return scraper
    return GenericScraper()

async def search_manga(query: str, limit: int = 10) -> List[MangaInfo]:
    # Use MangaDex for comprehensive search catalog
    md = MangaDexScraper()
    return await md.search(query, limit=limit)
