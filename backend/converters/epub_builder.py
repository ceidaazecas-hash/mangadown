import os
import io
import zipfile
import uuid
import html
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageOps

def _process_chapter_images_worker(item: Tuple[int, str, List[Any], bool]) -> List[Dict[str, Any]]:
    ch_idx, ch_title, ch_images, kindle_opt = item
    results = []

    for img_idx, img_item in enumerate(ch_images):
        try:
            if isinstance(img_item, (bytes, bytearray)):
                raw_bytes = bytes(img_item)
            elif isinstance(img_item, str) and os.path.exists(img_item):
                with open(img_item, "rb") as f:
                    raw_bytes = f.read()
            else:
                continue

            with Image.open(io.BytesIO(raw_bytes)) as img:
                img = ImageOps.exif_transpose(img)
                w, h = img.size
                ratio = h / w

                if ratio <= 1.8:
                    # Standard Manga Page: Fast single-pass prepare
                    out_io = io.BytesIO()
                    if kindle_opt and (w > 1440 or h > 1920):
                        img.thumbnail((1440, 1920), Image.Resampling.BILINEAR)
                        w, h = img.size

                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    img.save(out_io, format="JPEG", quality=86, optimize=False)
                    jpeg_bytes = out_io.getvalue()
                    results.append({
                        "ch_idx": ch_idx,
                        "img_idx": img_idx,
                        "slice_idx": 0,
                        "chapter_title": ch_title,
                        "is_chapter_start": (img_idx == 0),
                        "width": w,
                        "height": h,
                        "bytes": jpeg_bytes
                    })

                else:
                    # Webtoon Long Strip: Auto-slice into full-screen standard pages
                    slice_h = int(w * 1.45)
                    y = 0
                    slice_count = 0
                    while y < h:
                        end_y = min(y + slice_h, h)
                        if (h - end_y) < (slice_h * 0.22) and end_y < h:
                            end_y = h

                        crop = img.crop((0, y, w, end_y))
                        cw, ch_h = crop.size

                        if kindle_opt and (cw > 1440 or ch_h > 1920):
                            crop.thumbnail((1440, 1920), Image.Resampling.BILINEAR)
                            cw, ch_h = crop.size

                        if crop.mode != "RGB":
                            crop = crop.convert("RGB")

                        out_io = io.BytesIO()
                        crop.save(out_io, format="JPEG", quality=86, optimize=False)
                        jpeg_bytes = out_io.getvalue()

                        results.append({
                            "ch_idx": ch_idx,
                            "img_idx": img_idx,
                            "slice_idx": slice_count,
                            "chapter_title": ch_title,
                            "is_chapter_start": (img_idx == 0 and slice_count == 0),
                            "width": cw,
                            "height": ch_h,
                            "bytes": jpeg_bytes
                        })
                        slice_count += 1
                        y = end_y

        except Exception:
            continue

    return results

class EPUBBuilder:
    @staticmethod
    def build_epub(
        manga_title: str,
        chapters_data: List[Dict[str, Any]],
        output_path: str,
        author: str = "MangaDrop",
        language: str = "en",
        kindle_optimize: bool = True
    ) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        book_uuid = str(uuid.uuid4())
        safe_title = html.escape(manga_title)
        safe_author = html.escape(author or "Unknown Author")

        chapter_tasks = []
        for ch_idx, ch in enumerate(chapters_data):
            ch_title = ch.get("title") or ch.get("chapter_display") or f"Chapter {ch_idx+1}"
            ch_images = ch.get("images", [])
            if ch_images:
                chapter_tasks.append((ch_idx, ch_title, ch_images, kindle_optimize))

        if not chapter_tasks:
            raise ValueError("No chapters or pages found to build EPUB.")

        # Multi-core parallel image processing & slicing
        num_threads = min(32, max(8, (os.cpu_count() or 4) * 2))
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            nested_pages = list(pool.map(_process_chapter_images_worker, chapter_tasks))

        # Flatten & sort in exact chapter order
        pages_info = []
        for ch_pages in nested_pages:
            pages_info.extend(ch_pages)

        if not pages_info:
            raise ValueError("No valid pages found to build EPUB.")

        # Assign global page counters & filenames
        for idx, p in enumerate(pages_info, start=1):
            p["page_num"] = idx
            p["img_filename"] = f"img_{idx:04d}.jpg"
            p["xhtml_filename"] = f"page_{idx:04d}.xhtml"

        # Build EPUB Archive
        with zipfile.ZipFile(output_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

            manifest_items = [
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            ]
            spine_items = []
            nav_toc_items = []
            ncx_nav_points = []
            nav_play_order = 1

            for idx, p in enumerate(pages_info):
                p_num = p["page_num"]
                is_cover = (idx == 0)
                cover_prop = ' properties="cover-image"' if is_cover else ""
                
                manifest_items.append(f'<item id="img_{p_num}" href="images/{p["img_filename"]}" media-type="image/jpeg"{cover_prop}/>')
                manifest_items.append(f'<item id="xhtml_{p_num}" href="xhtml/{p["xhtml_filename"]}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="xhtml_{p_num}"/>')

                if p["is_chapter_start"] or idx == 0:
                    safe_ch_title = html.escape(p["chapter_title"])
                    nav_toc_items.append(f'<li><a href="xhtml/{p["xhtml_filename"]}">{safe_ch_title}</a></li>')
                    ncx_nav_points.append(f"""  <navPoint id="navPoint-{nav_play_order}" playOrder="{nav_play_order}">
    <navLabel><text>{safe_ch_title}</text></navLabel>
    <content src="xhtml/{p['xhtml_filename']}"/>
  </navPoint>""")
                    nav_play_order += 1

                # INSTANT write: JPEGs are already compressed, store directly without re-deflating!
                epub.writestr(f"OEBPS/images/{p['img_filename']}", p["bytes"], compress_type=zipfile.ZIP_STORED)
                
                page_html = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width={p['width']}, height={p['height']}"/>
  <title>{safe_title} - Page {p_num}</title>
  <style type="text/css">
    @page {{ margin: 0; padding: 0; }}
    html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background-color: #000; }}
    .page-wrap {{ display: flex; align-items: center; justify-content: center; width: 100vw; height: 100vh; }}
    img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block; }}
  </style>
</head>
<body>
  <div class="page-wrap">
    <img src="../images/{p['img_filename']}" alt="Page {p_num}"/>
  </div>
</body>
</html>"""
                epub.writestr(f"OEBPS/xhtml/{p['xhtml_filename']}", page_html, compress_type=zipfile.ZIP_STORED)

            content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{book_uuid}</dc:identifier>
    <dc:title>{safe_title}</dc:title>
    <dc:creator>{safe_author}</dc:creator>
    <dc:language>{language or 'en'}</dc:language>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta name="cover" content="img_1"/>
  </metadata>
  <manifest>
    {' '.join(manifest_items)}
  </manifest>
  <spine toc="ncx" page-progression-direction="ltr">
    {' '.join(spine_items)}
  </spine>
</package>"""
            epub.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)

            nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <meta charset="utf-8"/>
  <title>Table of Contents</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol>
      {' '.join(nav_toc_items)}
    </ol>
  </nav>
</body>
</html>"""
            epub.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_uuid}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="{len(pages_info)}"/>
    <meta name="dtb:maxPageNumber" content="{len(pages_info)}"/>
  </head>
  <docTitle><text>{safe_title}</text></docTitle>
  <navMap>
    {' '.join(ncx_nav_points)}
  </navMap>
</ncx>"""
            epub.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)

        return output_path
