import re
import asyncio
from typing import List, Optional, Dict, Any
import httpx
from .base import BaseScraper, MangaInfo, ChapterInfo, PageInfo

class MangaDexScraper(BaseScraper):
    name = "mangadex"
    BASE_API = "https://api.mangadex.org"
    COVERS_BASE = "https://uploads.mangadex.org/covers"

    def can_handle(self, url: str) -> bool:
        return bool(
            "mangadex.org" in url or
            re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", url.strip())
        )

    def extract_manga_id(self, url_or_id: str) -> str:
        text = url_or_id.strip()
        uuid_pattern = r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
        m = re.search(uuid_pattern, text)
        if m:
            return m.group(1)
        return text

    async def get_manga_info(self, url_or_id: str, language: str = "en") -> MangaInfo:
        clean_input = url_or_id.strip()
        
        async with self.create_client() as client:
            # Check if input is a chapter link
            if "/chapter/" in clean_input:
                ch_id = self.extract_manga_id(clean_input)
                ch_resp = await client.get(f"{self.BASE_API}/chapter/{ch_id}")
                if ch_resp.status_code == 200:
                    ch_data = ch_resp.json()
                    for rel in ch_data.get("data", {}).get("relationships", []):
                        if rel.get("type") == "manga":
                            clean_input = rel.get("id")
                            break

            manga_id = self.extract_manga_id(clean_input)
            
            # Fetch manga metadata
            resp = await client.get(
                f"{self.BASE_API}/manga/{manga_id}",
                params={"includes[]": ["cover_art", "author", "artist"]}
            )
            if resp.status_code != 200:
                raise ValueError(f"MangaDex returned error {resp.status_code}: {resp.text}")

            data = resp.json().get("data", {})
            attributes = data.get("attributes", {})
            relationships = data.get("relationships", [])

            # Extract Title
            titles_dict = attributes.get("title", {})
            title = titles_dict.get("en") or next(iter(titles_dict.values()), "Unknown Title")
            
            # Extract Synopsis
            desc_dict = attributes.get("description", {})
            synopsis = desc_dict.get("en") or next(iter(desc_dict.values()), "")

            # Extract Author, Artist, Cover
            author = ""
            artist = ""
            cover_filename = ""
            for rel in relationships:
                rel_type = rel.get("type")
                rel_attrs = rel.get("attributes", {})
                if rel_type == "author" and not author:
                    author = rel_attrs.get("name", "")
                elif rel_type == "artist" and not artist:
                    artist = rel_attrs.get("name", "")
                elif rel_type == "cover_art" and not cover_filename:
                    cover_filename = rel_attrs.get("fileName", "")

            cover_url = f"{self.COVERS_BASE}/{manga_id}/{cover_filename}.512.jpg" if cover_filename else ""
            status = attributes.get("status", "unknown").capitalize()
            genres = [
                tag.get("attributes", {}).get("name", {}).get("en", "")
                for tag in attributes.get("tags", [])
                if tag.get("attributes", {}).get("name", {}).get("en")
            ]

            # Fetch all chapters (paginated)
            chapters: List[ChapterInfo] = []
            available_langs = set()
            
            offset = 0
            limit = 100
            
            while True:
                params = {
                    "limit": limit,
                    "offset": offset,
                    "order[chapter]": "asc",
                    "includes[]": ["scanlation_group"],
                    "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"],
                }
                if language and language.lower() != "all":
                    params["translatedLanguage[]"] = [language.lower()]

                ch_resp = await client.get(f"{self.BASE_API}/manga/{manga_id}/feed", params=params)
                if ch_resp.status_code != 200:
                    break

                ch_json = ch_resp.json()
                ch_list = ch_json.get("data", [])
                total = ch_json.get("total", 0)

                for item in ch_list:
                    ch_attrs = item.get("attributes", {})
                    ch_rels = item.get("relationships", [])
                    
                    lang = ch_attrs.get("translatedLanguage", "en")
                    available_langs.add(lang)

                    ch_num_raw = ch_attrs.get("chapter")
                    if ch_num_raw is None or ch_num_raw == "":
                        ch_num = 0.0
                        ch_display = "Oneshot"
                    else:
                        try:
                            ch_num = float(ch_num_raw)
                            ch_display = f"Ch. {ch_num_raw}"
                        except ValueError:
                            ch_num = 0.0
                            ch_display = f"Ch. {ch_num_raw}"

                    # Group name
                    group_name = "No Group"
                    for r in ch_rels:
                        if r.get("type") == "scanlation_group":
                            group_name = r.get("attributes", {}).get("name", "No Group")
                            break

                    external_url = ch_attrs.get("externalUrl")
                    page_count = ch_attrs.get("pages", 0)

                    chapter = ChapterInfo(
                        id=item.get("id"),
                        chapter_number=ch_num,
                        chapter_display=ch_display,
                        title=ch_attrs.get("title") or "",
                        volume=ch_attrs.get("volume"),
                        language=lang,
                        scanlation_group=group_name,
                        publish_date=ch_attrs.get("publishAt", "")[:10] if ch_attrs.get("publishAt") else None,
                        url=f"https://mangadex.org/chapter/{item.get('id')}",
                        page_count=page_count,
                        source_name=self.name,
                        extra={"manga_id": manga_id, "external_url": external_url}
                    )
                    chapters.append(chapter)

                offset += limit
                if offset >= total or len(ch_list) == 0:
                    break

            chapters.sort(key=lambda c: (c.chapter_number, c.publish_date or ""))

            return MangaInfo(
                id=manga_id,
                title=title,
                url=f"https://mangadex.org/title/{manga_id}",
                source_name=self.name,
                cover_url=cover_url,
                synopsis=synopsis,
                author=author,
                artist=artist,
                status=status,
                genres=genres,
                available_languages=sorted(list(available_langs)) or ["en"],
                chapters=chapters,
                extra={"mangadex_id": manga_id}
            )

    async def get_chapter_pages(self, chapter: ChapterInfo, data_saver: bool = False) -> List[PageInfo]:
        # If chapter has an external link and 0 hosted pages, return empty list
        if chapter.extra and chapter.extra.get("external_url"):
            return []

        async with self.create_client() as client:
            resp = await client.get(f"{self.BASE_API}/at-home/server/{chapter.id}")
            if resp.status_code != 200:
                return []

            data = resp.json()
            base_url = data.get("baseUrl")
            ch_data = data.get("chapter", {})
            ch_hash = ch_data.get("hash")
            
            if not base_url or not ch_hash:
                return []

            mode_key = "dataSaver" if data_saver else "data"
            folder = "data-saver" if data_saver else "data"
            filenames = ch_data.get(mode_key, []) or ch_data.get("data", [])

            pages = []
            for idx, filename in enumerate(filenames, start=1):
                page_url = f"{base_url}/{folder}/{ch_hash}/{filename}"
                pages.append(PageInfo(
                    page_number=idx,
                    url=page_url,
                    filename=filename,
                    headers={"Referer": "https://mangadex.org/"}
                ))

            return pages

    async def search(self, query: str, limit: int = 10) -> List[MangaInfo]:
        async with self.create_client() as client:
            resp = await client.get(
                f"{self.BASE_API}/manga",
                params={
                    "title": query,
                    "limit": limit,
                    "includes[]": ["cover_art", "author"],
                    "order[relevance]": "desc",
                    "contentRating[]": ["safe", "suggestive", "erotica"]
                }
            )
            if resp.status_code != 200:
                return []

            results = []
            items = resp.json().get("data", [])
            for item in items:
                manga_id = item.get("id")
                attrs = item.get("attributes", {})
                rels = item.get("relationships", [])

                titles_dict = attrs.get("title", {})
                title = titles_dict.get("en") or next(iter(titles_dict.values()), "Unknown Title")
                
                desc_dict = attrs.get("description", {})
                synopsis = desc_dict.get("en") or next(iter(desc_dict.values()), "")

                cover_filename = ""
                author = ""
                for rel in rels:
                    if rel.get("type") == "cover_art":
                        cover_filename = rel.get("attributes", {}).get("fileName", "")
                    elif rel.get("type") == "author":
                        author = rel.get("attributes", {}).get("name", "")

                cover_url = f"{self.COVERS_BASE}/{manga_id}/{cover_filename}.256.jpg" if cover_filename else ""
                
                genres = [
                    tag.get("attributes", {}).get("name", {}).get("en", "")
                    for tag in attrs.get("tags", [])
                    if tag.get("attributes", {}).get("name", {}).get("en")
                ]

                results.append(MangaInfo(
                    id=manga_id,
                    title=title,
                    url=f"https://mangadex.org/title/{manga_id}",
                    source_name=self.name,
                    cover_url=cover_url,
                    synopsis=synopsis,
                    author=author,
                    status=attrs.get("status", "").capitalize(),
                    genres=genres[:4],
                    chapters=[]
                ))
            return results
