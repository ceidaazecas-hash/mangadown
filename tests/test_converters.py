import os
import io
import zipfile
import pytest
from PIL import Image
from pypdf import PdfReader

from backend.converters.pdf_builder import PDFBuilder
from backend.converters.epub_builder import EPUBBuilder
from backend.converters.cbz_builder import CBZBuilder

def create_dummy_image(width=800, height=1200, color="red") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

def test_pdf_builder(tmp_path):
    img1 = create_dummy_image(800, 1200, "blue")
    img2 = create_dummy_image(800, 1200, "green")
    img3 = create_dummy_image(1000, 1400, "yellow")

    chapters_data = [
        {
            "title": "Chapter 1: The Beginning",
            "chapter_display": "Ch. 1",
            "images": [img1, img2]
        },
        {
            "title": "Chapter 2: The Journey",
            "chapter_display": "Ch. 2",
            "images": [img3]
        }
    ]

    out_pdf = str(tmp_path / "test_manga.pdf")
    res_path = PDFBuilder.build_pdf(
        manga_title="Test Manga Series",
        chapters_data=chapters_data,
        output_path=out_pdf,
        author="Eiichiro Oda"
    )

    assert os.path.exists(res_path)
    assert os.path.getsize(res_path) > 1000

    # Verify with PdfReader
    reader = PdfReader(res_path)
    assert len(reader.pages) == 3
    assert len(reader.outline) >= 2
    # Verify outlines match chapter titles
    outline_titles = [item.title for item in reader.outline if hasattr(item, "title")]
    assert "Chapter 1: The Beginning" in outline_titles
    assert "Chapter 2: The Journey" in outline_titles

def test_epub_builder(tmp_path):
    img1 = create_dummy_image(800, 1200, "purple")
    img2 = create_dummy_image(800, 1200, "orange")

    chapters_data = [
        {
            "title": "Chapter 1",
            "chapter_display": "Ch. 1",
            "images": [img1, img2]
        }
    ]

    out_epub = str(tmp_path / "test_manga.epub")
    res_path = EPUBBuilder.build_epub(
        manga_title="Test EPUB Manga",
        chapters_data=chapters_data,
        output_path=out_epub,
        author="Akira Toriyama"
    )

    assert os.path.exists(res_path)
    
    # Check EPUB ZIP structure
    with zipfile.ZipFile(res_path, "r") as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert z.read("mimetype") == b"application/epub+zip"
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names
        assert "OEBPS/nav.xhtml" in names
        assert "OEBPS/toc.ncx" in names
        assert "OEBPS/xhtml/page_0001.xhtml" in names
        assert "OEBPS/xhtml/page_0002.xhtml" in names
        assert "OEBPS/images/img_0001.jpg" in names

def test_cbz_builder(tmp_path):
    img1 = create_dummy_image(800, 1200, "white")
    chapters_data = [
        {
            "title": "Chapter 1",
            "chapter_display": "Ch. 1",
            "images": [img1]
        }
    ]

    out_cbz = str(tmp_path / "test_manga.cbz")
    res_path = CBZBuilder.build_cbz(
        manga_title="Test CBZ Manga",
        chapters_data=chapters_data,
        output_path=out_cbz,
        author="Author"
    )

    assert os.path.exists(res_path)
    with zipfile.ZipFile(res_path, "r") as z:
        names = z.namelist()
        assert "ComicInfo.xml" in names
        assert "page_0001.jpg" in names
