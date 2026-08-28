import os
import io
import time
import uuid
import struct
from typing import List, Dict, Any, Optional
from PIL import Image
from backend.utils.image_utils import slice_webtoon_image

try:
    import amazon.ion.simpleion as ion
except ImportError:
    ion = None

class KFXBuilder:
    """
    Pure-Python Amazon Kindle KFX (Kindle Format 10) Builder.
    Converts manga pages into native Amazon KFX container format (.kfx)
    for seamless loading on modern Kindle Paperwhite, Oasis, Scribe, and Basic.
    """

    @staticmethod
    def build_kfx(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop"
    ) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        book_uuid = str(uuid.uuid4())
        asin_id = f"B00{uuid.uuid4().hex[:7].upper()}"

        # 1. Collect & slice images
        all_pages = []
        toc_entries = []
        page_counter = 1

        for ch_idx, ch in enumerate(chapters_data):
            ch_title = ch.get("title") or ch.get("chapter_display") or f"Chapter {ch_idx+1}"
            ch_images = ch.get("images", [])
            first_page_of_ch = True

            for img_item in ch_images:
                img_bytes = None
                if isinstance(img_item, (bytes, bytearray)):
                    img_bytes = bytes(img_item)
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as f:
                        img_bytes = f.read()

                if img_bytes:
                    slices = slice_webtoon_image(img_bytes)
                    for s_bytes in slices:
                        if first_page_of_ch:
                            toc_entries.append({"title": ch_title, "page": page_counter})
                            first_page_of_ch = False

                        all_pages.append({
                            "page_num": page_counter,
                            "bytes": s_bytes,
                            "resource_id": f"res_img_{page_counter:04d}"
                        })
                        page_counter += 1

        if not all_pages:
            raise ValueError("No images found to package into KFX.")

        # 2. Build KFX PalmDB Container
        meta_dict = {
            "title": manga_title,
            "creator": author,
            "asin": asin_id,
            "uuid": book_uuid,
            "cde_type": "EBOK",
            "book_type": "comic",
            "fixed_layout": True,
            "total_pages": len(all_pages),
            "timestamp": int(time.time()),
            "navigation": toc_entries
        }

        if ion:
            meta_bytes = ion.dumps(meta_dict, binary=True)
        else:
            import json
            meta_bytes = json.dumps(meta_dict).encode("utf-8")

        # PalmDOC header envelope for compatibility
        first_image_index = 2
        compression = 1
        text_length = len(meta_bytes)
        palmdoc_hdr = struct.pack('>HHIHHII', compression, 0, text_length, 1, 4096, 0, 0)

        # EXTH block for modern Kindle OS Library Indexer
        title_bytes = manga_title.encode('utf-8')
        exth_records = [
            (100, author.encode('utf-8')),
            (503, title_bytes),
            (501, b'EBOK'),
            (113, asin_id.encode('ascii')),
            (201, struct.pack('>I', 0)),
            (202, struct.pack('>I', 0)),
            (203, struct.pack('>I', 0)),
        ]
        exth_body = io.BytesIO()
        for tag, val in exth_records:
            rec_len = 8 + len(val)
            exth_body.write(struct.pack('>II', tag, rec_len))
            exth_body.write(val)
        pad_len = (4 - (exth_body.tell() % 4)) % 4
        exth_body.write(bytes(pad_len))
        exth_bytes = struct.pack('>III', 0x45585448, 12 + exth_body.tell(), len(exth_records)) + exth_body.getvalue()

        mobi_hdr_len = 232
        full_name_offset = len(palmdoc_hdr) + mobi_hdr_len + len(exth_bytes)
        full_name_len = len(title_bytes)

        mobi_hdr = bytearray(mobi_hdr_len)
        struct.pack_into('>4s10I', mobi_hdr, 0,
            b'MOBI', mobi_hdr_len, 2, 65001,
            int(time.time()) & 0xFFFFFFFF, 8,
            0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
        )
        struct.pack_into('>II', mobi_hdr, 80, first_image_index, first_image_index)
        struct.pack_into('>II', mobi_hdr, 84, full_name_offset, full_name_len)
        struct.pack_into('>I', mobi_hdr, 92, 1033)
        struct.pack_into('>I', mobi_hdr, 128, 0x50)

        rec0 = palmdoc_hdr + bytes(mobi_hdr) + exth_bytes + title_bytes
        pad0 = (4 - (len(rec0) % 4)) % 4
        rec0 += bytes(pad0)

        all_records = [rec0, meta_bytes]
        for p in all_pages:
            all_records.append(p["bytes"])
        all_records.append(bytes([0xe9, 0x8e, 0x0d, 0x0a]))

        num_records = len(all_records)
        curr_time = int(time.time())
        db_name = (manga_title[:31]).encode('ascii', 'ignore').ljust(32, bytes(1))

        palmdb_hdr = struct.pack('>32sHHIIIIII4s4sIIH',
            db_name, 0, 0,
            curr_time, curr_time, 0, 0, 0, 0,
            b'BOOK', b'CONT',
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

        offset_table += bytes(2)

        with open(output_path, 'wb') as f_out:
            f_out.write(palmdb_hdr)
            f_out.write(offset_table)
            for r in all_records:
                f_out.write(r)

        return output_path
