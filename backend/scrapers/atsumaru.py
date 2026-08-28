import re
from urllib.parse import urljoin, urlparse
from typing import List, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo

class AtsumaruScraper(BaseScraper):
    name = "atsumaru"
    BASE_URL = "https://atsu.moe"
    API_BASE = "https://atsu.moe/api"

    def can_handle(self, url: str) -> bool:
        return "atsu.moe" in url

    def extract_manga_id(self, url: str) -> str:
        # e.g. https://atsu.moe/manga/NW88G?filter=all or https://atsu.moe/read/NW88G/JjH9h
        m = re.search(r"/(?:manga|read)/([a-zA-Z0-9_-]+)", url)
        if m:
            return m.group(1)
        return url.strip().split("/")[-1].split("?")[0]

    async def get_manga_info(self, url: str, language: str = "en") -> MangaInfo:
        manga_id = self.extract_manga_id(url)
        headers = dict(self.headers)
        headers["Referer"] = "https://atsu.moe/"

        async with self.create_client(extra_headers=headers) as client:
            # 1. Fetch manga page metadata via API
            resp = await client.get(f"{self.API_BASE}/manga/page?id={manga_id}")
            if resp.status_code != 200:
                raise ValueError(f"Failed to load Atsumaru manga ({resp.status_code}): {url}")

            data = resp.json().get("mangaPage", {})
            title = data.get("title") or data.get("englishTitle") or "Unknown Manga"
            synopsis = data.get("synopsis") or ""
            status = data.get("status") or "Ongoing"
            
            # Authors
            authors_list = [a.get("name") for a in data.get("authors", []) if a.get("name")]
            author = ", ".join(authors_list) if authors_list else "Unknown"

            # Genres / Tags
            genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
            tags = [t.get("name") for t in data.get("tags", []) if t.get("name")]
            all_genres = list(dict.fromkeys(genres + tags))

            # Cover
            poster_data = data.get("poster")
            cover_path = ""
            if isinstance(poster_data, dict):
                cover_path = poster_data.get("largeImage") or poster_data.get("mediumImage") or poster_data.get("image") or poster_data.get("id") or ""
            elif isinstance(poster_data, str):
                cover_path = poster_data

            if cover_path:
                if not cover_path.startswith("http"):
                    cover_url = f"{self.BASE_URL}/static/{cover_path.lstrip('/')}" if not cover_path.startswith("static/") else f"{self.BASE_URL}/{cover_path}"
                else:
                    cover_url = cover_path
            else:
                cover_url = ""

            # 2. Fetch all chapters via API
            ch_resp = await client.get(f"{self.API_BASE}/manga/allChapters?mangaId={manga_id}")
            chapters: List[ChapterInfo] = []
            
            if ch_resp.status_code == 200:
                ch_json = ch_resp.json().get("chapters", [])
                scanlator_map = {s.get("id"): s.get("name") for s in data.get("scanlators", []) if isinstance(s, dict)}

                for item in ch_json:
                    ch_id = item.get("id")
                    ch_num_raw = item.get("number")
                    try:
                        ch_num = float(ch_num_raw) if ch_num_raw is not None else 0.0
                    except (ValueError, TypeError):
                        ch_num = 0.0

                    ch_title = item.get("title") or f"Chapter {ch_num:g}"
                    scan_id = item.get("scanlationMangaId")
                    group_name = scanlator_map.get(scan_id, "Atsumaru")
                    page_count = item.get("pageCount") or 0

                    chapters.append(ChapterInfo(
                        id=ch_id,
                        chapter_number=ch_num,
                        chapter_display=f"Ch. {ch_num:g}" if ch_num > 0 else ch_title,
                        title=ch_title,
                        language="en",
                        scanlation_group=group_name,
                        publish_date=None,
                        url=f"{self.BASE_URL}/read/{manga_id}/{ch_id}",
                        page_count=page_count,
                        source_name=self.name,
                        extra={"manga_id": manga_id, "chapter_id": ch_id}
                    ))

            # Sort chapters in ascending numerical order
            chapters.sort(key=lambda c: (c.chapter_number, c.id))

            return MangaInfo(
                id=manga_id,
                title=title,
                url=f"{self.BASE_URL}/manga/{manga_id}",
                source_name=self.name,
                cover_url=cover_url,
                synopsis=synopsis,
                author=author,
                status=status,
                genres=all_genres[:6],
                available_languages=["en"],
                chapters=chapters,
                extra={"atsumaru_id": manga_id}
            )

    async def get_chapter_pages(self, chapter: ChapterInfo) -> List[PageInfo]:
        manga_id = chapter.extra.get("manga_id") or self.extract_manga_id(chapter.url)
        ch_id = chapter.extra.get("chapter_id") or chapter.id

        headers = dict(self.headers)
        headers["Referer"] = f"{self.BASE_URL}/read/{manga_id}/{ch_id}"

        async with self.create_client(extra_headers=headers) as client:
            resp = await client.get(f"{self.API_BASE}/read/chapter?mangaId={manga_id}&chapterId={ch_id}")
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch Atsumaru chapter pages ({resp.status_code})")

            data = resp.json().get("readChapter", {})
            raw_pages = data.get("pages", [])
            
            pages: List[PageInfo] = []
            for idx, p in enumerate(raw_pages, start=1):
                img_path = p.get("image") or ""
                if not img_path:
                    continue
                full_img_url = urljoin(self.BASE_URL, img_path)
                pages.append(PageInfo(
                    page_number=idx,
                    url=full_img_url,
                    headers={"Referer": "https://atsu.moe/", "User-Agent": self.headers["User-Agent"]}
                ))

            return pages
