import os
import io
import zipfile
import html
from typing import List, Dict, Any
from backend.utils.image_utils import prepare_image_for_pdf

class CBZBuilder:
    @staticmethod
    def build_cbz(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop"
    ) -> str:
        """
        Builds a CBZ comic archive with ComicInfo.xml metadata.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        safe_title = html.escape(manga_title)
        safe_author = html.escape(author or "Unknown")

        global_page_counter = 1
        pages = []

        for ch_idx, ch in enumerate(chapters_data):
            ch_num_disp = ch.get("chapter_display") or f"Ch.{ch_idx+1}"
            ch_images = ch.get("images", [])

            for img_idx, img_item in enumerate(ch_images):
                if isinstance(img_item, (bytes, bytearray)):
                    raw_bytes = bytes(img_item)
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as f:
                        raw_bytes = f.read()
                else:
                    continue

                processed = prepare_image_for_pdf(raw_bytes)
                out_io = io.BytesIO()
                processed.save(out_io, format="JPEG", quality=92)
                jpeg_bytes = out_io.getvalue()
                processed.close()

                filename = f"page_{global_page_counter:04d}.jpg"
                pages.append((filename, jpeg_bytes))
                global_page_counter += 1

        if not pages:
            raise ValueError("No images found to build CBZ.")

        comic_info_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Series>{safe_title}</Series>
  <Writer>{safe_author}</Writer>
  <PageCount>{len(pages)}</PageCount>
  <Manga>YesAndRightToLeft</Manga>
</ComicInfo>"""

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as cbz:
            cbz.writestr("ComicInfo.xml", comic_info_xml)
            for fname, img_bytes in pages:
                cbz.writestr(fname, img_bytes)

        return output_path
