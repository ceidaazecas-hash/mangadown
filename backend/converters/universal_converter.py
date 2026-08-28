import os
import io
import re
import zipfile
import struct
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

from backend.converters.pdf_builder import PDFBuilder
from backend.converters.epub_builder import EPUBBuilder
from backend.converters.mobi_builder import MOBIBuilder
from backend.converters.cbz_builder import CBZBuilder
from backend.converters.kfx_builder import KFXBuilder

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

class UniversalConverter:
    """
    Converts between AZW3, MOBI, EPUB, PDF, CBZ, and ZIP formats.
    Extracts all images from any source manga container and repackages
    into the desired target format with bookmarks and high quality.
    """

    @classmethod
    def extract_images_from_file(cls, file_path: str) -> Tuple[str, List[bytes]]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        ext = os.path.splitext(file_path)[1].lower()

        images: List[bytes] = []

        if ext in (".epub", ".cbz", ".zip"):
            images = cls._extract_from_zip(file_path)
        elif ext in (".azw3", ".azw", ".mobi", ".prc", ".kfx"):
            images = cls._extract_from_palmdb(file_path)
        elif ext == ".pdf":
            images = cls._extract_from_pdf(file_path)
        else:
            # Fallback: try zip then palmdb
            try:
                images = cls._extract_from_zip(file_path)
            except Exception:
                images = cls._extract_from_palmdb(file_path)

        if not images:
            raise ValueError(f"Could not extract any images from {os.path.basename(file_path)}.")

        return base_name, images

    @classmethod
    def _extract_from_zip(cls, file_path: str) -> List[bytes]:
        images = []
        valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
        with zipfile.ZipFile(file_path, "r") as zf:
            file_list = [f for f in zf.namelist() if os.path.splitext(f.lower())[1] in valid_exts]
            file_list.sort(key=natural_sort_key)
            for fname in file_list:
                img_data = zf.read(fname)
                if len(img_data) > 100:
                    images.append(img_data)
        return images

    @classmethod
    def _extract_from_palmdb(cls, file_path: str) -> List[bytes]:
        images = []
        with open(file_path, "rb") as f:
            header = f.read(78)
            if len(header) < 78 or header[60:68] != b"BOOKMOBI":
                return cls._scan_raw_images(f)

            num_records = struct.unpack_from(">H", header, 76)[0]
            file_size = os.path.getsize(file_path)

            for entry_size in (8, 7):
                f.seek(78)
                offset_data = f.read(num_records * entry_size)
                if len(offset_data) < num_records * entry_size:
                    continue
                offsets = []
                for i in range(num_records):
                    off = struct.unpack_from(">I", offset_data, i * entry_size)[0]
                    offsets.append(off)
                offsets.append(file_size)

                candidate_images = []
                for i in range(2, num_records):
                    start = offsets[i]
                    length = offsets[i + 1] - start
                    if length <= 0 or start >= file_size:
                        continue
                    f.seek(start)
                    magic = f.read(min(16, length))
                    if magic.startswith(b"\xff\xd8\xff") or magic.startswith(b"\x89PNG") or magic.startswith(b"GIF8") or (magic.startswith(b"RIFF") and b"WEBP" in magic):
                        f.seek(start)
                        candidate_images.append(f.read(length))

                if candidate_images:
                    return candidate_images

        if not images:
            with open(file_path, "rb") as f:
                images = cls._scan_raw_images(f)

        return images

    @classmethod
    def _scan_raw_images(cls, f) -> List[bytes]:
        f.seek(0)
        data = f.read()
        images = []
        pos = 0
        while True:
            jpg_start = data.find(b"\xff\xd8\xff", pos)
            png_start = data.find(b"\x89PNG\r\n\x1a\n", pos)
            
            candidates = [p for p in [jpg_start, png_start] if p != -1]
            if not candidates:
                break
            
            start = min(candidates)
            if start == jpg_start:
                end = data.find(b"\xff\xd9", start + 4)
                if end != -1:
                    images.append(data[start:end+2])
                    pos = end + 2
                else:
                    pos = start + 4
            elif start == png_start:
                end = data.find(b"IEND\xaeB`\x82", start + 8)
                if end != -1:
                    images.append(data[start:end+8])
                    pos = end + 8
                else:
                    pos = start + 8
        return images

    @classmethod
    def _extract_from_pdf(cls, file_path: str) -> List[bytes]:
        from pypdf import PdfReader
        images = []
        reader = PdfReader(file_path)
        for page in reader.pages:
            for img_obj in page.images:
                images.append(img_obj.data)
        return images

    @classmethod
    def convert(
        cls,
        input_file_path: str,
        target_format: str,
        output_dir: str,
        custom_title: Optional[str] = None
    ) -> str:
        target_format = target_format.lower().strip().lstrip(".")
        if target_format not in ("pdf", "epub", "mobi", "azw3", "azw", "cbz", "kfx"):
            raise ValueError(f"Unsupported target format: {target_format}")

        title, images = cls.extract_images_from_file(input_file_path)
        if custom_title:
            title = custom_title

        os.makedirs(output_dir, exist_ok=True)
        out_filename = f"{title}.{target_format}"
        output_path = os.path.join(output_dir, out_filename)

        chapters_data = [
            {
                "title": title,
                "chapter_display": "Chapter 1",
                "images": images
            }
        ]

        if target_format == "pdf":
            PDFBuilder.build_pdf(title, chapters_data, output_path, author="Converted Manga")
        elif target_format == "epub":
            EPUBBuilder.build_epub(title, chapters_data, output_path, author="Converted Manga")
        elif target_format in ("mobi", "azw3", "azw"):
            MOBIBuilder.build_mobi(title, chapters_data, output_path, author="Converted Manga")
        elif target_format == "kfx":
            KFXBuilder.build_kfx(title, chapters_data, output_path, author="Converted Manga")
        elif target_format == "cbz":
            CBZBuilder.build_cbz(title, chapters_data, output_path, author="Converted Manga")

        return output_path

    @classmethod
    def split_and_convert(
        cls,
        input_file_path: str,
        target_format: str,
        output_dir: str,
        split_mode: str = "parts",
        split_value: int = 3,
        custom_title: Optional[str] = None
    ) -> List[str]:
        import math
        target_format = target_format.lower().strip().lstrip(".")
        if target_format not in ("pdf", "epub", "mobi", "azw3", "azw", "cbz", "kfx"):
            raise ValueError(f"Unsupported target format: {target_format}")

        title, images = cls.extract_images_from_file(input_file_path)
        if custom_title:
            title = custom_title

        total_pages = len(images)
        if total_pages == 0:
            raise ValueError("No images found to split.")

        if split_mode in ("auto", "auto_size") or (split_mode == "parts" and split_value == 0):
            # Dynamic Target Size (default: 25 MB for Email-Safe & Send-to-Kindle @kindle.com)
            target_mb = int(split_value) if (split_value and int(split_value) > 0) else 25
            
            if target_mb <= 25:
                # Strict 25 MB Email Attachment Hard Limit (Gmail, Outlook, Send-to-Kindle Email):
                # Set threshold to 22.5 MB so the final packaged file is strictly <= 23.5 MB (never bounces)!
                target_max_bytes = int(22.5 * 1024 * 1024)
            elif target_mb <= 50:
                target_max_bytes = int(46 * 1024 * 1024)
            else:
                # 200 MB Send-to-Kindle Web limit (180 MB safety threshold)
                target_max_bytes = int(180 * 1024 * 1024)
            
            volume_chunks = []
            curr_chunk = []
            curr_bytes = 0
            
            for img in images:
                img_size = len(img) if isinstance(img, (bytes, bytearray)) else 500 * 1024
                if curr_chunk and (curr_bytes + img_size > target_max_bytes):
                    volume_chunks.append(curr_chunk)
                    curr_chunk = [img]
                    curr_bytes = img_size
                else:
                    curr_chunk.append(img)
                    curr_bytes += img_size
            
            if curr_chunk:
                volume_chunks.append(curr_chunk)
        elif split_mode == "parts":
            num_parts = max(1, int(split_value))
            chunk_size = math.ceil(total_pages / num_parts)
            volume_chunks = [images[i:i + chunk_size] for i in range(0, total_pages, chunk_size)]
        else:
            chunk_size = max(1, int(split_value))
            volume_chunks = [images[i:i + chunk_size] for i in range(0, total_pages, chunk_size)]

        num_parts = len(volume_chunks)
        if num_parts > 1:
            target_dir = os.path.join(output_dir, f"{title} [Split Volumes]")
        else:
            target_dir = output_dir
            
        os.makedirs(target_dir, exist_ok=True)
        created_paths = []

        for part_idx, part_images in enumerate(volume_chunks):
            part_num = part_idx + 1
            part_title = f"{title} - Vol {part_num:02d} (of {num_parts})" if num_parts > 1 else title
            out_filename = f"{part_title}.{target_format}"
            output_path = os.path.join(target_dir, out_filename)

            chapters_data = [
                {
                    "title": part_title,
                    "chapter_display": f"Part {part_num}",
                    "images": part_images
                }
            ]

            if target_format == "pdf":
                PDFBuilder.build_pdf(part_title, chapters_data, output_path, author="Converted Manga")
            elif target_format == "epub":
                EPUBBuilder.build_epub(part_title, chapters_data, output_path, author="Converted Manga")
            elif target_format in ("mobi", "azw3", "azw"):
                MOBIBuilder.build_mobi(part_title, chapters_data, output_path, author="Converted Manga")
            elif target_format == "kfx":
                KFXBuilder.build_kfx(part_title, chapters_data, output_path, author="Converted Manga")
            elif target_format == "cbz":
                CBZBuilder.build_cbz(part_title, chapters_data, output_path, author="Converted Manga")

            created_paths.append(output_path)

        return created_paths

