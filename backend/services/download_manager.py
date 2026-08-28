import os
import io
import re
import uuid
import shutil
import zipfile
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
import httpx
import aiofiles

from backend.scrapers.base import MangaInfo, ChapterInfo, PageInfo
from backend.scrapers import get_scraper_for_url
from backend.converters.pdf_builder import PDFBuilder
from backend.converters.epub_builder import EPUBBuilder
from backend.converters.cbz_builder import CBZBuilder
from backend.converters.mobi_builder import MOBIBuilder
from backend.services.progress_tracker import ProgressTracker

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:100]

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

class DownloadManager:
    def __init__(self, download_dir: str = "downloads", max_concurrency: int = 45):
        self.download_dir = os.path.abspath(download_dir)
        self.max_concurrency = max_concurrency
        self.tracker = ProgressTracker()
        os.makedirs(self.download_dir, exist_ok=True)
        self.history: List[Dict[str, Any]] = []
        self.file_registry: Dict[str, str] = {}

    def register_file(self, file_id: str, file_path: str):
        self.file_registry[file_id] = file_path

    def get_file_path(self, file_id: str) -> Optional[str]:
        if file_id in self.file_registry and os.path.exists(self.file_registry[file_id]):
            return self.file_registry[file_id]
        for item in self.history:
            if item.get("file_id") == file_id and os.path.exists(item.get("file_path", "")):
                return item["file_path"]
        if os.path.exists(self.download_dir):
            for fname in os.listdir(self.download_dir):
                if fname.startswith(f"{file_id}_"):
                    return os.path.join(self.download_dir, fname)
                if fname == file_id or os.path.splitext(fname)[0] == file_id:
                    return os.path.join(self.download_dir, fname)
        return None

    async def _download_single_page(
        self,
        client: httpx.AsyncClient,
        page: PageInfo,
        save_path: str,
        semaphore: asyncio.Semaphore,
        retries: int = 3
    ) -> Tuple[bool, int]:
        async with semaphore:
            for attempt in range(retries):
                try:
                    headers = dict(page.headers)
                    if not headers.get("User-Agent"):
                        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

                    # High performance streaming download
                    async with client.stream("GET", page.url, headers=headers, timeout=25.0) as resp:
                        if resp.status_code == 200:
                            nbytes = 0
                            async with aiofiles.open(save_path, "wb") as f:
                                async for chunk in resp.aiter_bytes(chunk_size=65536):
                                    if chunk:
                                        await f.write(chunk)
                                        nbytes += len(chunk)
                            
                            if nbytes > 300:
                                return True, nbytes
                        elif resp.status_code in (429, 503, 504):
                            await asyncio.sleep(0.3 * (attempt + 1))
                except Exception:
                    if attempt == retries - 1:
                        return False, 0
                    await asyncio.sleep(0.3 * (attempt + 1))
            return False, 0

    async def process_download_task(
        self,
        task_id: str,
        manga: MangaInfo,
        selected_chapters: List[ChapterInfo],
        export_format: str = "pdf",
        bundle_mode: str = "single",
        data_saver: bool = False
    ):
        export_format = export_format.lower()
        bundle_mode = bundle_mode.lower()
        total_chapters = len(selected_chapters)
        
        self.tracker.update_task(
            task_id,
            status="scraping",
            message=f"Scanning {total_chapters} chapter(s) at turbo speed...",
            total_chapters=total_chapters
        )

        # Hidden temp workspace
        hidden_temp_root = os.path.join(os.path.dirname(self.download_dir), ".tmp_manga")
        os.makedirs(hidden_temp_root, exist_ok=True)
        task_temp_dir = os.path.join(hidden_temp_root, f"task_{task_id}")
        os.makedirs(task_temp_dir, exist_ok=True)

        try:
            # 1. PARALLEL CHAPTER SCANNING (HTTP/2 multiplexed)
            scraper = get_scraper_for_url(manga.url)
            scan_semaphore = asyncio.Semaphore(20)

            async def scan_single_chapter(idx: int, ch: ChapterInfo):
                async with scan_semaphore:
                    try:
                        if scraper.name == "mangadex" and hasattr(scraper, "get_chapter_pages"):
                            pages = await scraper.get_chapter_pages(ch, data_saver=data_saver)
                        else:
                            pages = await scraper.get_chapter_pages(ch)
                        
                        if not pages:
                            return None

                        ch_dir = os.path.join(task_temp_dir, f"ch_{idx+1:04d}")
                        os.makedirs(ch_dir, exist_ok=True)

                        return {
                            "index": idx,
                            "chapter": ch,
                            "title": f"{ch.chapter_display} - {ch.title}".strip(" -"),
                            "chapter_display": ch.chapter_display,
                            "pages": pages,
                            "dir": ch_dir,
                            "downloaded_files": []
                        }
                    except Exception:
                        return None

            scan_tasks = [scan_single_chapter(i, ch) for i, ch in enumerate(selected_chapters)]
            scan_results = await asyncio.gather(*scan_tasks)
            chapters_data = [res for res in scan_results if res is not None]
            chapters_data.sort(key=lambda x: x["index"])

            total_pages_overall = sum(len(cd["pages"]) for cd in chapters_data)

            if not chapters_data or total_pages_overall == 0:
                raise ValueError("No pages could be extracted from selected chapters.")

            self.tracker.update_task(
                task_id,
                status="downloading",
                total_pages_overall=total_pages_overall,
                message=f"🚀 Turbo Downloading {total_pages_overall} pages at maximum speed..."
            )

            # 2. ULTRA-FAST CONCURRENT PAGE DOWNLOADING (HTTP/2 + Connection Pooling)
            limits = httpx.Limits(max_connections=70, max_keepalive_connections=50, keepalive_expiry=120.0)
            dl_semaphore = asyncio.Semaphore(self.max_concurrency)
            
            downloaded_pages_count = 0
            total_bytes_downloaded = 0
            start_time = time.time()

            async with httpx.AsyncClient(
                http2=True,
                limits=limits,
                timeout=30.0,
                follow_redirects=True,
                verify=False
            ) as client:
                
                # Build all page download jobs across all chapters
                all_page_tasks = []
                for cd in chapters_data:
                    for p in cd["pages"]:
                        save_path = os.path.join(cd["dir"], f"p_{p.page_number:04d}.jpg")
                        all_page_tasks.append((cd, p, save_path))

                async def download_worker(cd_ref, p_info, save_file):
                    nonlocal downloaded_pages_count, total_bytes_downloaded
                    
                    task = self.tracker.get_task(task_id)
                    if task and task.is_cancelled:
                        raise asyncio.CancelledError()

                    ok, nbytes = await self._download_single_page(client, p_info, save_file, dl_semaphore)
                    if ok:
                        cd_ref["downloaded_files"].append(save_file)
                        downloaded_pages_count += 1
                        total_bytes_downloaded += nbytes

                    # Live Speed in Mbps & MB/s
                    elapsed = max(0.1, time.time() - start_time)
                    speed_mbps = ((total_bytes_downloaded * 8) / (1000 * 1000)) / elapsed
                    speed_mbytes = (total_bytes_downloaded / (1024 * 1024)) / elapsed
                    pages_sec = downloaded_pages_count / elapsed

                    pct = (downloaded_pages_count / total_pages_overall) * 85.0
                    self.tracker.update_task(
                        task_id,
                        current_page=downloaded_pages_count,
                        total_pages_downloaded=downloaded_pages_count,
                        progress_percent=round(pct, 1),
                        current_chapter=cd_ref["chapter_display"],
                        message=f"⚡ {speed_mbps:.1f} Mbps ({speed_mbytes:.1f} MB/s) • {downloaded_pages_count}/{total_pages_overall} pages ({pages_sec:.1f} p/s)"
                    )

                # Fire all parallel workers concurrently!
                await asyncio.gather(*[download_worker(cd, p, sp) for cd, p, sp in all_page_tasks])

            # Sort downloaded files per chapter
            for cd in chapters_data:
                cd["downloaded_files"].sort()

            # 3. MULTI-THREADED COMPILATION
            self.tracker.update_task(
                task_id,
                status="packaging",
                progress_percent=88.0,
                message=f"Compiling {export_format.upper()} document across CPU cores..."
            )

            safe_manga_title = sanitize_filename(manga.title)
            ch_start = selected_chapters[0].chapter_display
            ch_end = selected_chapters[-1].chapter_display
            range_str = f"{ch_start}" if len(selected_chapters) == 1 else f"{ch_start}-{ch_end}"
            range_str = sanitize_filename(range_str)
            
            file_id = str(uuid.uuid4())

            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=max(4, os.cpu_count() or 4)) as pool:
                if bundle_mode == "single":
                    out_filename = f"{safe_manga_title} ({range_str}).{export_format}"
                    final_output_path = os.path.join(self.download_dir, out_filename)
                    self.register_file(file_id, final_output_path)

                    builder_data = [
                        {
                            "title": cd["title"],
                            "chapter_display": cd["chapter_display"],
                            "images": cd["downloaded_files"]
                        }
                        for cd in chapters_data if cd["downloaded_files"]
                    ]

                    if export_format == "pdf":
                        await loop.run_in_executor(
                            pool, PDFBuilder.build_pdf,
                            manga.title, builder_data, final_output_path, manga.author or "Unknown"
                        )
                    elif export_format == "epub":
                        await loop.run_in_executor(
                            pool, EPUBBuilder.build_epub,
                            manga.title, builder_data, final_output_path, manga.author or "Unknown"
                        )
                    elif export_format in ("mobi", "azw3", "azw"):
                        await loop.run_in_executor(
                            pool, MOBIBuilder.build_mobi,
                            manga.title, builder_data, final_output_path, manga.author or "Unknown"
                        )
                    elif export_format == "cbz":
                        await loop.run_in_executor(
                            pool, CBZBuilder.build_cbz,
                            manga.title, builder_data, final_output_path, manga.author or "Unknown"
                        )

                else:
                    out_filename = f"{safe_manga_title} ({range_str}) - {export_format.upper()}s.zip"
                    final_output_path = os.path.join(self.download_dir, out_filename)
                    self.register_file(file_id, final_output_path)
                    
                    zip_temp_dir = os.path.join(task_temp_dir, "individual_files")
                    os.makedirs(zip_temp_dir, exist_ok=True)
                    individual_files = []

                    for cd in chapters_data:
                        if not cd["downloaded_files"]:
                            continue
                        ch_fname = f"{safe_manga_title}_{sanitize_filename(cd['chapter_display'])}.{export_format}"
                        ch_out_path = os.path.join(zip_temp_dir, ch_fname)
                        single_ch_data = [{
                            "title": cd["title"],
                            "chapter_display": cd["chapter_display"],
                            "images": cd["downloaded_files"]
                        }]

                        if export_format == "pdf":
                            await loop.run_in_executor(pool, PDFBuilder.build_pdf, manga.title, single_ch_data, ch_out_path, manga.author)
                        elif export_format == "epub":
                            await loop.run_in_executor(pool, EPUBBuilder.build_epub, manga.title, single_ch_data, ch_out_path, manga.author)
                        elif export_format in ("mobi", "azw3", "azw"):
                            await loop.run_in_executor(pool, MOBIBuilder.build_mobi, manga.title, single_ch_data, ch_out_path, manga.author)
                        elif export_format == "cbz":
                            await loop.run_in_executor(pool, CBZBuilder.build_cbz, manga.title, single_ch_data, ch_out_path, manga.author)

                        individual_files.append((ch_fname, ch_out_path))

                    with zipfile.ZipFile(final_output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for ch_fname, ch_path in individual_files:
                            zf.write(ch_path, arcname=ch_fname)

            file_size = os.path.getsize(final_output_path)
            size_formatted = format_file_size(file_size)

            history_entry = {
                "file_id": file_id,
                "manga_title": manga.title,
                "filename": out_filename,
                "format": export_format.upper(),
                "bundle_mode": bundle_mode,
                "chapter_range": range_str,
                "chapter_count": len(selected_chapters),
                "file_size": size_formatted,
                "file_path": final_output_path,
                "download_url": f"/api/files/{file_id}",
                "timestamp": time.time()
            }
            self.history.insert(0, history_entry)

            self.tracker.update_task(
                task_id,
                status="completed",
                progress_percent=100.0,
                message="Download & Packaging complete!",
                file_id=file_id,
                filename=out_filename,
                file_size_bytes=file_size,
                file_size_formatted=size_formatted
            )

        except asyncio.CancelledError:
            self.tracker.update_task(task_id, status="cancelled", message="Task cancelled.")
        except Exception as e:
            self.tracker.update_task(
                task_id,
                status="error",
                message=f"Failed: {str(e)}",
                error_message=str(e)
            )
        finally:
            if os.path.exists(task_temp_dir):
                shutil.rmtree(task_temp_dir, ignore_errors=True)
