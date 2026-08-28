import os
import asyncio
import pytest
from backend.scrapers.mangadex import MangaDexScraper
from backend.services.download_manager import DownloadManager
from backend.services.progress_tracker import ProgressTracker

@pytest.mark.asyncio
async def test_e2e_download_pdf_and_epub(tmp_path):
    dl_mgr = DownloadManager(download_dir=str(tmp_path))
    tracker = ProgressTracker()
    md = MangaDexScraper()

    # Search Bocchi the Rock
    results = await md.search("Bocchi the Rock", limit=1)
    assert len(results) > 0
    manga_id = results[0].id

    # Get manga info
    manga_info = await md.get_manga_info(manga_id)
    assert len(manga_info.chapters) > 0

    # Pick first chapter with pages > 0
    test_ch = None
    for c in manga_info.chapters:
        if c.page_count and c.page_count > 0:
            test_ch = c
            break

    assert test_ch is not None, "Should find at least one hosted chapter"

    # Test PDF download
    task_id_pdf = "test_task_pdf_1"
    tracker.create_task(task_id_pdf, manga_info.title, "pdf", "single", 1)
    
    await dl_mgr.process_download_task(
        task_id=task_id_pdf,
        manga=manga_info,
        selected_chapters=[test_ch],
        export_format="pdf",
        bundle_mode="single",
        data_saver=True
    )

    pdf_task = tracker.get_task(task_id_pdf)
    assert pdf_task.status == "completed", f"PDF task failed: {pdf_task.error_message}"
    assert pdf_task.file_size_bytes > 50000

    # Test EPUB download
    task_id_epub = "test_task_epub_1"
    tracker.create_task(task_id_epub, manga_info.title, "epub", "single", 1)
    
    await dl_mgr.process_download_task(
        task_id=task_id_epub,
        manga=manga_info,
        selected_chapters=[test_ch],
        export_format="epub",
        bundle_mode="single",
        data_saver=True
    )

    epub_task = tracker.get_task(task_id_epub)
    assert epub_task.status == "completed", f"EPUB task failed: {epub_task.error_message}"
    assert epub_task.file_size_bytes > 50000
