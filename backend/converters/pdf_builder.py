import os
import io
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
from pypdf import PdfWriter, PdfReader
from backend.utils.image_utils import prepare_image_for_pdf, slice_webtoon_image

def _load_and_prepare_img(img_item: Any) -> Optional[Image.Image]:
    try:
        if isinstance(img_item, (bytes, bytearray)):
            return prepare_image_for_pdf(bytes(img_item))
        elif isinstance(img_item, str) and os.path.exists(img_item):
            with open(img_item, "rb") as f:
                return prepare_image_for_pdf(f.read())
        return None
    except Exception:
        return None

class PDFBuilder:
    @staticmethod
    def build_pdf(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop"
    ) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Flatten all image tasks with chapter bookmarks & auto-slice webtoons
        all_img_tasks = []
        chapter_start_pages: List[Tuple[str, int]] = []
        page_counter = 0

        for ch in chapters_data:
            ch_title = ch.get("title") or ch.get("chapter_display") or "Chapter"
            chapter_start_pages.append((ch_title, page_counter))
            
            for img_item in ch.get("images", []):
                if isinstance(img_item, (bytes, bytearray)):
                    raw_b = bytes(img_item)
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as f:
                        raw_b = f.read()
                else:
                    continue

                slices = slice_webtoon_image(raw_b)
                for s in slices:
                    all_img_tasks.append(s)
                    page_counter += 1

        if not all_img_tasks:
            raise ValueError("No images provided to build PDF.")

        # Process images concurrently using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(4, os.cpu_count() or 4)) as pool:
            pil_images = list(filter(None, pool.map(_load_and_prepare_img, all_img_tasks)))

        if not pil_images:
            raise ValueError("Failed to load any valid images for PDF.")

        # Save multi-page PDF
        temp_pdf_io = io.BytesIO()
        first_img = pil_images[0]
        rest_imgs = pil_images[1:] if len(pil_images) > 1 else []
        
        first_img.save(
            temp_pdf_io,
            format="PDF",
            save_all=True,
            append_images=rest_imgs,
            resolution=100.0
        )
        temp_pdf_io.seek(0)

        # Add bookmarks and metadata
        reader = PdfReader(temp_pdf_io)
        writer = PdfWriter()
        writer.append(reader)

        for ch_title, page_idx in chapter_start_pages:
            if page_idx < len(writer.pages):
                writer.add_outline_item(title=ch_title, page_number=page_idx)

        writer.add_metadata({
            "/Title": manga_title,
            "/Author": author or "Unknown",
            "/Subject": f"{manga_title} - Downloaded via MangaDrop",
            "/Creator": "MangaDrop Turbo Downloader"
        })

        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        for img in pil_images:
            img.close()

        return output_path
