import re
from typing import List
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo

class MangaFreakScraper(BaseScraper):
    name = "mangafreak"

    def can_handle(self, url: str) -> bool:
        return "mangafreak.net" in url or "mangafreak.me" in url

    async def get_manga_info(self, url: str, language: str = "en") -> MangaInfo:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch {url}: status {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")

            title_elem = soup.select_one("div.manga_series_data h1, div.manga_series_data h5")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Manga"

            cover_elem = soup.select_one("div.manga_series_image img")
            cover_url = cover_elem.get("src", "") if cover_elem else ""
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url

            desc_elem = soup.select_one("div.manga_series_description p")
            synopsis = desc_elem.get_text(strip=True) if desc_elem else ""

            status = "Ongoing"
            author = "Unknown"
            genres = []
            
            for row in soup.select("div.manga_series_data div"):
                text = row.get_text()
                if "Status:" in text:
                    status = text.replace("Status:", "").strip()
                elif "Author:" in text:
                    author = text.replace("Author:", "").strip()
                elif "Genre:" in text:
                    genres = [g.strip() for g in text.replace("Genre:", "").split(",") if g.strip()]

            chapters: List[ChapterInfo] = []
            ch_rows = soup.select("div.manga_series_list tbody tr")
            for row in ch_rows:
                link = row.select_one("td a")
                if not link:
                    continue
                ch_url = link.get("href", "")
                if not ch_url.startswith("http"):
                    ch_url = "https://w16.mangafreak.net" + ch_url
                
                ch_title = link.get_text(strip=True)
                match = re.search(r"Chapter\s*([\d\.]+)", ch_title, re.IGNORECASE)
                if match:
                    try:
                        ch_num = float(match.group(1))
                    except ValueError:
                        ch_num = 0.0
                else:
                    ch_num = 0.0

                ch_display = f"Ch. {ch_num:g}" if ch_num > 0 else ch_title
                date_td = row.select("td")[-1] if len(row.select("td")) > 1 else None
                publish_date = date_td.get_text(strip=True) if date_td else None

                chapters.append(ChapterInfo(
                    id=ch_url,
                    chapter_number=ch_num,
                    chapter_display=ch_display,
                    title=ch_title,
                    language="en",
                    scanlation_group="MangaFreak",
                    publish_date=publish_date,
                    url=ch_url,
                    source_name=self.name
                ))

            chapters.sort(key=lambda c: c.chapter_number)

            return MangaInfo(
                id=url,
                title=title,
                url=url,
                source_name=self.name,
                cover_url=cover_url,
                synopsis=synopsis,
                author=author,
                status=status,
                genres=genres,
                available_languages=["en"],
                chapters=chapters
            )

    async def get_chapter_pages(self, chapter: ChapterInfo) -> List[PageInfo]:
        headers = dict(self.headers)
        headers["Referer"] = chapter.url

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
            resp = await client.get(chapter.url)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch chapter page: {chapter.url}")

            soup = BeautifulSoup(resp.text, "html.parser")
            img_elems = soup.select("div.mySlides img#gohere, div.mySlides img, div.read_img img")
            
            pages: List[PageInfo] = []
            for idx, img in enumerate(img_elems, start=1):
                src = img.get("src")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    pages.append(PageInfo(
                        page_number=idx,
                        url=src,
                        headers={"Referer": chapter.url, "User-Agent": self.headers["User-Agent"]}
                    ))

            return pages
