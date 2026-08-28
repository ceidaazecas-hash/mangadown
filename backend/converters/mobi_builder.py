import os
import io
import time
import struct
from typing import List, Dict, Any, Optional
from PIL import Image
from backend.utils.image_utils import slice_webtoon_image

class MOBIBuilder:
    """
    Pure-Python Amazon Kindle MOBI / AZW / PRC Builder.
    Converts manga pages into PalmDOC PalmDB MOBI 6 format
    that is natively supported for direct download by Kindle Experimental Browser.
    """

    @staticmethod
    def build_mobi(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop"
    ) -> str:
        """
        Builds a standard PalmDOC / MOBI-6 format eBook from manga images.
        Compatible natively with Amazon Kindle e-readers (.mobi / .azw3).
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. Prepare HTML and Image Records
        all_images = []
        html_parts = [
            '<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>',
            f'<title>{manga_title}</title></head><body>',
            f'<h1 style="text-align:center;">{manga_title}</h1>',
        ]

        img_idx = 1
        for ch in chapters_data:
            ch_title = ch.get("title") or ch.get("chapter_display") or "Chapter"
            html_parts.append(f'<div class="chapter"><h2 style="font-size:18px;margin-bottom:10px;">{ch_title}</h2>')

            for img_item in ch.get("images", []):
                img_bytes = None
                if isinstance(img_item, (bytes, bytearray)):
                    img_bytes = bytes(img_item)
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as f:
                        img_bytes = f.read()

                if img_bytes:
                    slices = slice_webtoon_image(img_bytes)
                    for s_bytes in slices:
                        all_images.append(s_bytes)
                        html_parts.append(f'<div style="page-break-before:always;text-align:center;"><img recindex="{img_idx:05d}" /></div>')
                        img_idx += 1

            html_parts.append('</div>')

        html_parts.append('</body></html>')
        html_bytes = ''.join(html_parts).encode('utf-8')

        if not all_images:
            raise ValueError("No images found to package into MOBI/AZW.")

        # 2. Build PalmDOC Header
        first_image_index = 2
        compression = 1 # No compression
        text_length = len(html_bytes)
        record_count = 1
        record_size = 4096
        palmdoc_hdr = struct.pack('>HHIHHII', compression, 0, text_length, record_count, record_size, 0, 0)

        # 3. Build EXTH Header
        exth_records = []
        author_bytes = author.encode('utf-8')
        exth_records.append((100, author_bytes)) # Author
        title_bytes = manga_title.encode('utf-8')
        exth_records.append((503, title_bytes)) # Full Title
        exth_records.append((201, struct.pack('>I', 0))) # Cover image offset

        exth_body = io.BytesIO()
        for tag, val in exth_records:
            rec_len = 8 + len(val)
            exth_body.write(struct.pack('>II', tag, rec_len))
            exth_body.write(val)
        pad_len = (4 - (exth_body.tell() % 4)) % 4
        exth_body.write(b'\x00' * pad_len)

        exth_bytes = struct.pack('>III', 0x45585448, 12 + exth_body.tell(), len(exth_records)) + exth_body.getvalue()

        # 4. Build MOBI Header
        mobi_hdr_len = 232
        full_name_offset = len(palmdoc_hdr) + mobi_hdr_len + len(exth_bytes)
        full_name_len = len(title_bytes)

        mobi_hdr = bytearray(mobi_hdr_len)
        struct.pack_into('>4s10I', mobi_hdr, 0,
            b'MOBI',
            mobi_hdr_len,
            2, # Book type
            65001, # UTF-8
            int(time.time()) & 0xFFFFFFFF,
            6, # MOBI Version 6
            0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
            0xFFFFFFFF
        )
        struct.pack_into('>II', mobi_hdr, 80, first_image_index, first_image_index)
        struct.pack_into('>II', mobi_hdr, 84, full_name_offset, full_name_len)
        struct.pack_into('>I', mobi_hdr, 92, 1033) # Locale en
        struct.pack_into('>I', mobi_hdr, 128, 0x50) # EXTH flags

        rec0 = palmdoc_hdr + bytes(mobi_hdr) + exth_bytes + title_bytes
        rec0 += b'\x00' * ((4 - (len(rec0) % 4)) % 4)

        all_records = [rec0, html_bytes]
        for img_data in all_images:
            all_records.append(img_data)

        # EOF Record
        all_records.append(b'\xe9\x8e\r\n')

        # 5. Build PalmDB Header
        num_records = len(all_records)
        curr_time = int(time.time())
        db_name = (manga_title[:31]).encode('ascii', 'ignore').ljust(32, b'\x00')

        palmdb_hdr = struct.pack('>32sHHIIIIII4s4sIIH',
            db_name,
            0, 0,
            curr_time, curr_time, 0, 0, 0, 0,
            b'BOOK', b'MOBI',
            curr_time, 0,
            num_records
        )

        offset_table_len = num_records * 8 + 2
        first_offset = len(palmdb_hdr) + offset_table_len

        offsets = []
        curr_off = first_offset
        for r in all_records:
            offsets.append(curr_off)
            curr_off += len(r)

        offset_table = bytearray()
        for idx, off in enumerate(offsets):
            unique_id = (idx * 2) & 0xFFFFFF
            offset_table += struct.pack('>IBBH', off, 0, (unique_id >> 16) & 0xFF, unique_id & 0xFFFF)

        offset_table += b'\x00\x00'

        with open(output_path, 'wb') as f_out:
            f_out.write(palmdb_hdr)
            f_out.write(offset_table)
            for r in all_records:
                f_out.write(r)

        return output_path
