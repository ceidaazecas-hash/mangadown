import re
import json
from urllib.parse import urljoin, urlparse
from typing import List, Optional, Set
import httpx
from bs4 import BeautifulSoup
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo

class GenericScraper(BaseScraper):
    name = "generic"

    def can_handle(self, url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

    async def get_manga_info(self, url: str, language: str = "en") -> MangaInfo:
        parsed_origin = urlparse(url)
        origin_referer = f"{parsed_origin.scheme}://{parsed_origin.netloc}/"

        async with self.create_client(extra_headers={"Referer": origin_referer}) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch webpage ({resp.status_code}): {url}")

            soup = BeautifulSoup(resp.text, "html.parser")

            # 1. Title Extraction
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else ""
            if not title:
                h1 = soup.find("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else "Unknown Manga"

            # Clean common SEO suffixes
            title = re.sub(r"\s*[-|–:»]\s*(Read|Read Online|Manga|Free|Chapter|Scan|All Chapters|English|Raw).*$", "", title, flags=re.IGNORECASE).strip()

            # 2. Cover Image Extraction
            og_image = soup.find("meta", property="og:image")
            cover_url = og_image["content"].strip() if og_image and og_image.get("content") else ""
            if not cover_url:
                for selector in [
                    ".thumb img", ".poster img", ".cover img", ".manga-cover img",
                    ".series-thumb img", ".summary_image img", ".post-thumb img",
                    ".anime-thumbnail img", "div.imgdesc img"
                ]:
                    img = soup.select_one(selector)
                    if img:
                        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
                        if src:
                            cover_url = urljoin(url, src)
                            break

            # 3. Synopsis / Description
            og_desc = soup.find("meta", property="og:description")
            synopsis = og_desc["content"].strip() if og_desc and og_desc.get("content") else ""
            if not synopsis:
                desc_elem = soup.select_one(
                    ".description, .synopsis, .summary, .entry-content p, #synopsis, "
                    ".manga-excerpt, .post-content p, .story-info-right-extent"
                )
                if desc_elem:
                    synopsis = desc_elem.get_text(strip=True)

            # 4. Check for Madara WP-Manga Ajax Chapters
            # (WordPress Madara themes store manga ID in data-id or class)
            manga_id_elem = soup.select_one("div#manga-chapters-holder, div.wp-manga, input#wp-manga-id")
            madara_id = manga_id_elem.get("data-id") if manga_id_elem else None

            chapters: List[ChapterInfo] = []
            seen_urls: Set[str] = set()

            if madara_id:
                try:
                    ajax_url = urljoin(url, f"ajax/chapters/")
                    ajax_resp = await client.post(ajax_url)
                    if ajax_resp.status_code == 200 and len(ajax_resp.text) > 100:
                        ajax_soup = BeautifulSoup(ajax_resp.text, "html.parser")
                        chapters.extend(self._extract_chapters_from_soup(ajax_soup, url, seen_urls, parsed_origin.netloc))
                except Exception:
                    pass

            # 5. Extract chapters from the HTML directly
            if not chapters:
                chapters.extend(self._extract_chapters_from_soup(soup, url, seen_urls, parsed_origin.netloc))

            # 6. Check for dropdown select elements (e.g. <select id="chapter-select">)
            if not chapters:
                for select in soup.select("select.chapter-select, select#select-chapter, select.single-chapter-select, select[name*='chapter'], select.c-select"):
                    for opt in select.select("option"):
                        val = opt.get("value", "").strip()
                        opt_text = opt.get_text(strip=True)
                        if val and (val.startswith("http") or val.startswith("/")):
                            full_opt_url = urljoin(url, val)
                            if full_opt_url not in seen_urls:
                                seen_urls.add(full_opt_url)
                                ch_num = self._parse_chapter_number(opt_text, full_opt_url)
                                ch_disp = f"Ch. {ch_num:g}" if ch_num > 0 else opt_text
                                chapters.append(ChapterInfo(
                                    id=full_opt_url,
                                    chapter_number=ch_num,
                                    chapter_display=ch_disp,
                                    title=opt_text,
                                    language="en",
                                    scanlation_group=parsed_origin.netloc,
                                    url=full_opt_url,
                                    source_name=self.name
                                ))

            # 7. If this is a direct chapter reader URL and we found parent link, try fetching parent series!
            if (not chapters or len(chapters) <= 1) and ("chapter" in url.lower() or "ch-" in url.lower() or "ep-" in url.lower()):
                parent_link = soup.select_one(
                    "a.all-chapters, a.series-link, a.back-to-series, "
                    "ol.breadcrumb a[href*='manga'], ul.breadcrumb a[href*='series'], "
                    "div.nav-previous a, a[rel='category']"
                )
                if parent_link and parent_link.get("href"):
                    parent_url = urljoin(url, parent_link["href"])
                    if parent_url != url:
                        try:
                            parent_resp = await client.get(parent_url)
                            if parent_resp.status_code == 200:
                                parent_soup = BeautifulSoup(parent_resp.text, "html.parser")
                                parent_chapters = self._extract_chapters_from_soup(parent_soup, parent_url, seen_urls, parsed_origin.netloc)
                                if len(parent_chapters) > len(chapters):
                                    chapters = parent_chapters
                        except Exception:
                            pass

            # If still no chapters found, treat this single page as Chapter 1
            if not chapters:
                chapters.append(ChapterInfo(
                    id=url,
                    chapter_number=1.0,
                    chapter_display="Chapter 1 (Full)",
                    title=title,
                    language="en",
                    scanlation_group=parsed_origin.netloc,
                    url=url,
                    source_name=self.name
                ))
            else:
                chapters.sort(key=lambda c: c.chapter_number)

            return MangaInfo(
                id=url,
                title=title,
                url=url,
                source_name=self.name,
                cover_url=cover_url,
                synopsis=synopsis,
                author="Unknown",
                status="Unknown",
                genres=[],
                available_languages=["en"],
                chapters=chapters
            )

    def _extract_chapters_from_soup(self, soup: BeautifulSoup, base_url: str, seen_urls: Set[str], netloc: str) -> List[ChapterInfo]:
        chapters: List[ChapterInfo] = []
        
        # Priority selectors
        selectors = [
            "li.wp-manga-chapter a",
            "ul.sub-chap a",
            "div.chapter-list a",
            "div.chapters-list a",
            "div#chapterlist ul li a",
            "div.clstyle li a",
            "div.eph-num a",
            "ul.row-content-chapter a",
            "div.chapter-container a",
            "div.listing-chapters_sub-head a",
            "div.bxcl ul li a",
            "ul.chapter-list-inner a",
            "div.list-group a.list-group-item"
        ]

        found_links = []
        for selector in selectors:
            elems = soup.select(selector)
            if elems:
                found_links = elems
                break

        if not found_links:
            found_links = soup.find_all("a", href=True)

        for a in found_links:
            href = a.get("href", "")
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            text = a.get_text(strip=True)
            match_text = re.search(r"(?:chapter|ch\.?|episode|ep\.?)\s*([\d\.]+)", text, re.IGNORECASE)
            match_url = re.search(r"/(?:chapter|ch|ep|episode)[-_/]?([\d\.]+)", href, re.IGNORECASE)

            if match_text or match_url:
                num_str = match_text.group(1) if match_text else match_url.group(1)
                try:
                    ch_num = float(num_str)
                except ValueError:
                    ch_num = 0.0

                seen_urls.add(full_url)
                ch_disp = f"Ch. {num_str}"
                chapters.append(ChapterInfo(
                    id=full_url,
                    chapter_number=ch_num,
                    chapter_display=ch_disp,
                    title=text or ch_disp,
                    language="en",
                    scanlation_group=netloc,
                    url=full_url,
                    source_name=self.name
                ))

        return chapters

    def _parse_chapter_number(self, text: str, url: str) -> float:
        match = re.search(r"(?:chapter|ch\.?|episode|ep\.?)\s*([\d\.]+)", text, re.IGNORECASE)
        if not match:
            match = re.search(r"/(?:chapter|ch|ep|episode)[-_/]?([\d\.]+)", url, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0

    async def get_chapter_pages(self, chapter: ChapterInfo) -> List[PageInfo]:
        parsed_origin = urlparse(chapter.url)
        headers = dict(self.headers)
        headers["Referer"] = f"{parsed_origin.scheme}://{parsed_origin.netloc}/"

        async with self.create_client(extra_headers=headers) as client:
            resp = await client.get(chapter.url)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch chapter page ({resp.status_code}): {chapter.url}")

            soup = BeautifulSoup(resp.text, "html.parser")
            pages: List[PageInfo] = []
            seen_srcs: Set[str] = set()

            # 1. Check for embedded JS script image arrays
            # e.g., var pages = ["https://...jpg", ...];
            scripts = soup.find_all("script")
            for script in scripts:
                script_text = script.string or script.get_text() or ""
                if "http" in script_text and any(keyword in script_text for keyword in ["pages", "images", "chapter_images", "manga_pages", "sources", "ts_reader"]):
                    # Look for arrays of image URLs
                    found_urls = re.findall(r'["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp|avif)(?:\?[^"\']*)?)["\']', script_text)
                    if len(found_urls) > 3:
                        for u in found_urls:
                            clean_u = u.replace(r"\/", "/")
                            if clean_u not in seen_srcs:
                                seen_srcs.add(clean_u)
                                pages.append(PageInfo(
                                    page_number=len(pages) + 1,
                                    url=clean_u,
                                    headers={"Referer": chapter.url, "User-Agent": self.headers["User-Agent"]}
                                ))
                        if len(pages) > 0:
                            return pages

            # 2. Look for reader containers in HTML
            img_elems = soup.select(
                "div#reader img, div.reading-content img, div.reader-area img, "
                "div.container-chapter-reader img, div.page-break img, div.entry-content img, "
                "div.separator a img, div#chapter-images img, div.chapter-content img, "
                "div.iv-card img, div.chapter-video-frame img, div.vung-doc img"
            )

            if not img_elems:
                # Fallback: inspect all images on page
                img_elems = [
                    img for img in soup.find_all("img")
                    if not any(cls in (img.get("class") or []) for cls in ["avatar", "logo", "icon", "banner", "ad", "emoji"])
                ]

            for img in img_elems:
                src = (
                    img.get("src") or 
                    img.get("data-src") or 
                    img.get("data-original") or 
                    img.get("data-lazy-src") or 
                    img.get("data-url") or
                    img.get("data-full-url")
                )
                if not src:
                    srcset = img.get("srcset") or img.get("data-srcset")
                    if srcset:
                        src = srcset.split(",")[0].split(" ")[0].strip()

                if not src:
                    continue

                src = src.strip()
                if src.startswith("//"):
                    src = "https:" + src
                
                full_img_url = urljoin(chapter.url, src)

                # Filter out ads or tracking widgets
                if any(bad in full_img_url.lower() for bad in ["logo", "icon", "gravatar", "placeholder", "facebook", "twitter", "ads", "badge"]):
                    continue

                if full_img_url not in seen_srcs:
                    seen_srcs.add(full_img_url)
                    pages.append(PageInfo(
                        page_number=len(pages) + 1,
                        url=full_img_url,
                        headers={"Referer": chapter.url, "User-Agent": self.headers["User-Agent"]}
                    ))

            return pages
