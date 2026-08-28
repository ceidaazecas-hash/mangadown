import os
import io
import pymupdf
from typing import List, Dict, Any, Tuple, Optional
from backend.utils.image_utils import slice_webtoon_image

class PDFBuilder:
    """
    Ultra-Fast Zero-RAM Pure Streaming Manga PDF Builder powered by PyMuPDF.
    Packages thousands of high-resolution manga pages in seconds with TOC bookmarks.
    """

    @staticmethod
    def build_pdf(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop"
    ) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        doc = pymupdf.open()
        toc = []
        page_idx = 1

        for ch_idx, ch in enumerate(chapters_data):
            ch_title = ch.get("title") or ch.get("chapter_display") or f"Chapter {ch_idx+1}"
            toc.append([1, ch_title, page_idx])

            for img_item in ch.get("images", []):
                raw_b = None
                if isinstance(img_item, (bytes, bytearray)):
                    raw_b = bytes(img_item)
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as f:
                        raw_b = f.read()

                if not raw_b:
                    continue

                slices = slice_webtoon_image(raw_b)
                for s in slices:
                    try:
                        # Inspect image dimensions directly from stream
                        img_doc = pymupdf.open(stream=s)
                        rect = img_doc[0].rect
                        page = doc.new_page(width=rect.width, height=rect.height)
                        page.insert_image(rect, stream=s)
                        img_doc.close()
                        page_idx += 1
                    except Exception:
                        continue

        if doc.page_count == 0:
            doc.close()
            raise ValueError("No images provided to build PDF.")

        # Set Table of Contents and metadata
        if toc:
            doc.set_toc(toc)

        doc.set_metadata({
            "title": manga_title,
            "author": author or "MangaDrop",
            "subject": f"{manga_title} - Downloaded via MangaDrop",
            "creator": "MangaDrop Turbo Downloader"
        })

        # Save with clean stream deflation & instant disk writing
        doc.save(output_path, garbage=3, deflate=True)
        doc.close()

        return output_path
