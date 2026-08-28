import os
import json
import uuid
import asyncio
import shutil
import time
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.scrapers import get_scraper_for_url, search_manga
from backend.scrapers.base import MangaInfo, ChapterInfo
from backend.services.progress_tracker import ProgressTracker
from backend.services.download_manager import DownloadManager, sanitize_filename, format_file_size
from backend.services.kindle_service import KindleService

app = FastAPI(title="MangaDrop - Manga Downloader & Converter")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DOWNLOADS_DIR = "/tmp/manga_downloads"
else:
    DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

try:
    os.makedirs(STATIC_DIR, exist_ok=True)
except Exception:
    pass

try:
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
except Exception:
    DOWNLOADS_DIR = "/tmp/manga_downloads"
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

import socket

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

SERVER_BUILD_ID = str(int(time.time()))

@app.get("/api/version")
async def get_version():
    return {
        "version": "1.3.0",
        "build_id": SERVER_BUILD_ID
    }

@app.get("/kindle", response_class=HTMLResponse)
async def kindle_hub_view():
    kindle_html = os.path.join(FRONTEND_DIR, "kindle.html")
    if os.path.exists(kindle_html):
        with open(kindle_html, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Kindle Hub Ready</h1>")

import httpx

def make_short_url(target_url: str) -> str:
    try:
        r = httpx.get("https://ulvis.net/API/write/get", params={"url": target_url, "type": "json"}, verify=False, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and data.get("data", {}).get("url"):
                return data["data"]["url"]
    except Exception:
        pass
    try:
        r = httpx.get("https://clck.ru/--", params={"url": target_url}, verify=False, timeout=3.0)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception:
        pass
    return target_url

@app.get("/api/network/ip")
async def get_network_ip(request: Request):
    local_ip = get_local_ip()
    port = 8000
    hub_url = f"http://{local_ip}:{port}/kindle"
    
    origin = str(request.base_url).rstrip('/')
    public_k = f"{origin}/k"
    short_k = await asyncio.to_thread(make_short_url, public_k)

    return {
        "local_ip": local_ip,
        "port": port,
        "hub_url": hub_url,
        "public_k": public_k,
        "short_k": short_k
    }

tracker = ProgressTracker()
download_manager = DownloadManager(download_dir=DOWNLOADS_DIR)

# Request Models
class ScanRequest(BaseModel):
    url: str
    language: Optional[str] = "en"

class ChapterDownloadItem(BaseModel):
    id: str
    chapter_number: float
    chapter_display: str
    title: Optional[str] = ""
    volume: Optional[str] = None
    language: Optional[str] = "en"
    scanlation_group: Optional[str] = ""
    publish_date: Optional[str] = None
    url: Optional[str] = ""
    page_count: Optional[int] = None
    source_name: Optional[str] = ""
    extra: Optional[Dict[str, Any]] = {}

class MangaDownloadPayload(BaseModel):
    id: str
    title: str
    url: str
    source_name: str
    author: Optional[str] = ""
    artist: Optional[str] = ""
    cover_url: Optional[str] = ""
    status: Optional[str] = ""
    genres: Optional[List[str]] = []
    chapters: List[ChapterDownloadItem]

class DownloadRequest(BaseModel):
    manga: MangaDownloadPayload
    selected_chapter_ids: List[str]
    format: str = "pdf" # pdf, epub, cbz
    bundle_mode: str = "single" # single, zip
    data_saver: bool = False

@app.get("/k", include_in_schema=False)
async def kindle_short_redirect():
    return RedirectResponse(url="/kindle")

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    user_agent = request.headers.get("user-agent", "").lower()
    if "kindle" in user_agent or "silk" in user_agent:
        return RedirectResponse(url="/kindle")

    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Frontend index.html not found</h1>", status_code=404)

@app.post("/api/scan")
async def scan_url(req: ScanRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Manga URL or ID is required.")

    scraper = get_scraper_for_url(url)
    try:
        manga_info = await scraper.get_manga_info(url, language=req.language or "en")
        return asdict(manga_info)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scan manga: {str(e)}")

@app.get("/api/search")
async def search_mangas(q: str = Query(..., min_length=1), limit: int = 8):
    try:
        results = await search_manga(q, limit=limit)
        return [asdict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/api/download/start")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    
    # Filter selected chapters
    selected_ids_set = set(req.selected_chapter_ids)
    selected_ch_items = [ch for ch in req.manga.chapters if ch.id in selected_ids_set]
    
    if not selected_ch_items:
        raise HTTPException(status_code=400, detail="No valid chapters selected.")

    # Convert to ChapterInfo dataclass
    selected_chapters = [
        ChapterInfo(
            id=c.id,
            chapter_number=c.chapter_number,
            chapter_display=c.chapter_display,
            title=c.title or "",
            volume=c.volume,
            language=c.language or "en",
            scanlation_group=c.scanlation_group or "",
            publish_date=c.publish_date,
            url=c.url or "",
            page_count=c.page_count,
            source_name=c.source_name or req.manga.source_name,
            extra=c.extra or {}
        )
        for c in selected_ch_items
    ]

    manga_info = MangaInfo(
        id=req.manga.id,
        title=req.manga.title,
        url=req.manga.url,
        source_name=req.manga.source_name,
        cover_url=req.manga.cover_url or "",
        author=req.manga.author or "",
        artist=req.manga.artist or "",
        status=req.manga.status or "",
        genres=req.manga.genres or [],
        chapters=selected_chapters
    )

    # Initialize task in tracker
    tracker.create_task(
        task_id=task_id,
        manga_title=req.manga.title,
        format=req.format,
        bundle_mode=req.bundle_mode,
        total_chapters=len(selected_chapters)
    )

    # Dispatch download in background
    background_tasks.add_task(
        download_manager.process_download_task,
        task_id=task_id,
        manga=manga_info,
        selected_chapters=selected_chapters,
        export_format=req.format,
        bundle_mode=req.bundle_mode,
        data_saver=req.data_saver
    )

    return {"task_id": task_id, "total_chapters": len(selected_chapters)}

@app.get("/api/tasks/{task_id}/progress")
async def task_progress_stream(task_id: str):
    async def event_generator():
        async for event in tracker.subscribe(task_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    tracker.cancel_task(task_id)
    return {"message": "Task cancellation requested."}

@app.get("/api/files/{file_id}")
async def download_file(file_id: str):
    full_path = download_manager.get_file_path(file_id)
    if not full_path or not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found or expired.")

    original_filename = os.path.basename(full_path)
    if "_" in original_filename and len(original_filename.split("_")[0]) == 36:
        original_filename = original_filename.split("_", 1)[1]

    ext = os.path.splitext(original_filename)[-1].lower()
    if ext == ".epub":
        media_type = "application/epub+zip"
    elif ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".mobi", ".prc"):
        media_type = "application/x-mobipocket-ebook"
    elif ext in (".azw3", ".azw"):
        media_type = "application/vnd.amazon.ebook"
    elif ext == ".cbz":
        media_type = "application/vnd.comicbook+zip"
    elif ext == ".zip":
        media_type = "application/zip"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        full_path,
        filename=original_filename,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{original_filename}"'
        }
    )

class KindleSendRequest(BaseModel):
    file_id: str
    kindle_email: Optional[str] = "nit.ratha01_t9Ucaw@kindle.com"
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None

@app.post("/api/kindle/send")
async def send_to_kindle(req: KindleSendRequest):
    target_path = download_manager.get_file_path(req.file_id)
    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File not found or expired.")

    try:
        result = KindleService.send_to_kindle(
            file_path=target_path,
            kindle_email=req.kindle_email or "nit.ratha01_t9Ucaw@kindle.com",
            smtp_host=req.smtp_host,
            smtp_port=req.smtp_port or 587,
            smtp_user=req.smtp_user,
            smtp_password=req.smtp_password,
            from_email=req.from_email
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class KindleSplitRequest(BaseModel):
    file_id: str

@app.post("/api/kindle/split")
async def split_for_kindle(req: KindleSplitRequest):
    target_path = download_manager.get_file_path(req.file_id)
    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File not found or expired.")

    try:
        loop = asyncio.get_running_loop()
        volumes = await loop.run_in_executor(
            None,
            KindleService.optimize_and_split_epub,
            target_path,
            DOWNLOADS_DIR
        )

        for vol in volumes:
            download_manager.register_file(vol["file_id"], vol["file_path"])
            download_manager.history.insert(0, {
                "file_id": vol["file_id"],
                "manga_title": vol["filename"],
                "filename": vol["filename"],
                "format": "EPUB (Kindle)",
                "bundle_mode": "single",
                "chapter_range": f"Part {vol['part_number']} of {vol['total_parts']}",
                "chapter_count": 1,
                "file_size": vol["file_size"],
                "file_path": vol["file_path"],
                "download_url": vol["download_url"],
                "timestamp": time.time()
            })

        return {"success": True, "volumes": volumes}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/kindle/split/start")
async def start_kindle_split(req: KindleSplitRequest, background_tasks: BackgroundTasks):
    target_path = download_manager.get_file_path(req.file_id)
    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File not found or expired.")

    task_id = f"split_{str(uuid.uuid4())[:8]}"
    tracker.create_task(
        task_id=task_id,
        manga_title="Kindle Splitting",
        format="epub",
        bundle_mode="single",
        total_chapters=1
    )

    def run_background_split():
        try:
            volumes = KindleService.optimize_and_split_epub(
                file_path=target_path,
                output_dir=DOWNLOADS_DIR,
                tracker=tracker,
                task_id=task_id
            )

            for vol in volumes:
                download_manager.register_file(vol["file_id"], vol["file_path"])
                download_manager.history.insert(0, {
                    "file_id": vol["file_id"],
                    "manga_title": vol["filename"],
                    "filename": vol["filename"],
                    "format": "EPUB (Kindle)",
                    "bundle_mode": "single",
                    "chapter_range": f"Part {vol['part_number']} of {vol['total_parts']}",
                    "chapter_count": 1,
                    "file_size": vol["file_size"],
                    "file_path": vol["file_path"],
                    "download_url": vol["download_url"],
                    "timestamp": time.time()
                })

            tracker.update_task(
                task_id,
                status="completed",
                progress_percent=100.0,
                message=f"Split complete! Created {len(volumes)} Kindle volumes.",
                extra={"volumes": volumes}
            )
        except Exception as e:
            tracker.update_task(
                task_id,
                status="error",
                message=str(e),
                error_message=str(e)
            )

    background_tasks.add_task(run_background_split)
    return {"task_id": task_id}

@app.post("/api/kindle/upload")
async def upload_file_for_kindle(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        original_name = file.filename or "uploaded_book.epub"
        safe_fname = sanitize_filename(original_name)
        save_path = os.path.join(DOWNLOADS_DIR, f"{file_id}_{safe_fname}")

        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(save_path)
        size_formatted = format_file_size(file_size)

        entry = {
            "file_id": file_id,
            "manga_title": safe_fname,
            "filename": safe_fname,
            "format": safe_fname.split(".")[-1].upper() if "." in safe_fname else "FILE",
            "bundle_mode": "single",
            "chapter_range": "Uploaded File",
            "chapter_count": 1,
            "file_size": size_formatted,
            "file_path": save_path,
            "download_url": f"/api/files/{file_id}",
            "timestamp": time.time()
        }
        download_manager.history.insert(0, entry)

        return {
            "file_id": file_id,
            "filename": safe_fname,
            "file_size": size_formatted,
            "download_url": f"/api/files/{file_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    return download_manager.history

@app.post("/api/history/clear")
async def clear_history():
    download_manager.history.clear()
    return {"message": "History cleared."}
