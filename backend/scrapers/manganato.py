import re
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo

class ManganatoScraper(BaseScraper):
    name = "manganato"

    def can_handle(self, url: str) -> bool:
        domain_patterns = ["manganato.com", "chapmanganato.to", "chapmanganato.com", "mangakakalot.com", "mangakakalot.tv", "natomanga.com"]
        return any(domain in url for domain in domain_patterns)

    async def get_manga_info(self, url: str, language: str = "en") -> MangaInfo:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch {url}: status {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract Title
            title_elem = soup.select_one("div.story-info-right h1, div.manga-info-top h1, div.story-info-right h2")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Manga"

            # Extract Cover
            cover_elem = soup.select_one("span.info-image img, div.manga-info-pic img, div.story-info-left img")
            cover_url = cover_elem.get("src", "") if cover_elem else ""

            # Extract Description
            desc_elem = soup.select_one("div#panel-story-info-description, div#noidungm, div.story-info-right-extent")
            synopsis = ""
            if desc_elem:
                # remove "Description :" label if present
                synopsis = desc_elem.get_text(strip=True).replace("Description :", "").replace("Description:", "").strip()

            # Extract Author, Status, Genres
            author = ""
            status = "Unknown"
            genres = []
            
            for row in soup.select("table.variations-tableInfo tr, ul.manga-info-top-ul li"):
                text = row.get_text()
                if "Author" in text:
                    author_links = row.select("a")
                    author = ", ".join([a.get_text(strip=True) for a in author_links]) or row.get_text(strip=True)
                elif "Status" in text:
                    status = row.select_one("td.table-value, a, span")
                    status = status.get_text(strip=True) if status else "Ongoing"
                elif "Genres" in text:
                    genres = [a.get_text(strip=True) for a in row.select("a")]

            # Extract Chapters
            chapters: List[ChapterInfo] = []
            ch_links = soup.select("ul.row-content-chapter li a.chapter-name, div.chapter-list div.row span a")
            
            for link in ch_links:
                ch_url = link.get("href", "")
                ch_title = link.get_text(strip=True)
                
                # Parse chapter number
                ch_num = 0.0
                match = re.search(r"(?:chapter|ch\.?)\s*([\d\.]+)", ch_title, re.IGNORECASE)
                if not match:
                    match = re.search(r"(?:chapter|ch\.?)[-_]([\d\.]+)", ch_url, re.IGNORECASE)
                if match:
                    try:
                        ch_num = float(match.group(1))
                    except ValueError:
                        ch_num = 0.0

                ch_display = f"Ch. {ch_num:g}" if ch_num > 0 else ch_title

                parent_li = link.find_parent("li") or link.find_parent("div", class_="row")
                date_elem = parent_li.select_one("span.chapter-time, span.time") if parent_li else None
                publish_date = date_elem.get_text(strip=True) if date_elem else None

                chapters.append(ChapterInfo(
                    id=ch_url,
                    chapter_number=ch_num,
                    chapter_display=ch_display,
                    title=ch_title,
                    language="en",
                    scanlation_group="Manganato",
                    publish_date=publish_date,
                    url=ch_url,
                    source_name=self.name
                ))

            # Manganato lists newest chapters first -> reverse to get ascending order
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
            img_elems = soup.select("div.container-chapter-reader img, div.panel-read-story img")
            
            pages: List[PageInfo] = []
            for idx, img in enumerate(img_elems, start=1):
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if src:
                    # Clean up URL
                    src = src.strip()
                    pages.append(PageInfo(
                        page_number=idx,
                        url=src,
                        headers={"Referer": chapter.url, "User-Agent": self.headers["User-Agent"]}
                    ))

            return pages
