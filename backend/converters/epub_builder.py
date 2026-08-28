import os
import io
import zipfile
import uuid
import html
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
from backend.utils.image_utils import prepare_image_for_pdf, optimize_for_kindle

def _process_epub_page(item: Tuple[int, str, bool, Any, bool]) -> Optional[Dict[str, Any]]:
    global_page_counter, ch_title, is_chapter_start, img_item, kindle_opt = item
    try:
        if isinstance(img_item, (bytes, bytearray)):
            raw_bytes = bytes(img_item)
        elif isinstance(img_item, str) and os.path.exists(img_item):
            with open(img_item, "rb") as f:
                raw_bytes = f.read()
        else:
            return None

        if kindle_opt:
            jpeg_bytes, w, h = optimize_for_kindle(raw_bytes)
        else:
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                w, h = pil_img.size

            processed_img = prepare_image_for_pdf(raw_bytes)
            out_io = io.BytesIO()
            processed_img.save(out_io, format="JPEG", quality=90, optimize=True)
            jpeg_bytes = out_io.getvalue()
            processed_img.close()

        img_filename = f"img_{global_page_counter:04d}.jpg"

        return {
            "page_num": global_page_counter,
            "chapter_title": ch_title,
            "is_chapter_start": is_chapter_start,
            "img_filename": img_filename,
            "xhtml_filename": f"page_{global_page_counter:04d}.xhtml",
            "width": w,
            "height": h,
            "bytes": jpeg_bytes
        }
    except Exception:
        return None

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

        tasks = []
        global_page_counter = 1

        for ch_idx, ch in enumerate(chapters_data):
            ch_title = ch.get("title") or ch.get("chapter_display") or f"Chapter {ch_idx+1}"
            ch_images = ch.get("images", [])
            
            for img_idx, img_item in enumerate(ch_images):
                is_start = (img_idx == 0)
                tasks.append((global_page_counter, ch_title, is_start, img_item, kindle_optimize))
                global_page_counter += 1

        if not tasks:
            raise ValueError("No pages found to build EPUB.")

        with ThreadPoolExecutor(max_workers=max(4, os.cpu_count() or 4)) as pool:
            pages_info = list(filter(None, pool.map(_process_epub_page, tasks)))

        if not pages_info:
            raise ValueError("No valid pages found to build EPUB.")

        pages_info.sort(key=lambda x: x["page_num"])

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

                epub.writestr(f"OEBPS/images/{p['img_filename']}", p["bytes"], compress_type=zipfile.ZIP_DEFLATED)
                
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
                epub.writestr(f"OEBPS/xhtml/{p['xhtml_filename']}", page_html, compress_type=zipfile.ZIP_DEFLATED)

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
