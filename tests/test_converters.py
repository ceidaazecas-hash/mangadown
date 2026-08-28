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

def test_mobi_builder(tmp_path):
    from backend.converters.mobi_builder import MOBIBuilder
    img1 = create_dummy_image(800, 1200, "cyan")
    chapters_data = [
        {
            "title": "Chapter 1",
            "chapter_display": "Ch. 1",
            "images": [img1]
        }
    ]

    out_mobi = str(tmp_path / "test_manga.mobi")
    res_path = MOBIBuilder.build_mobi(
        manga_title="Test MOBI Manga",
        chapters_data=chapters_data,
        output_path=out_mobi,
        author="Kindle Author"
    )

    assert os.path.exists(res_path)
    assert os.path.getsize(res_path) > 1000
    with open(res_path, "rb") as f:
        header = f.read(68)
        assert b"BOOKMOBI" in header

def test_universal_converter(tmp_path):
    from backend.converters.universal_converter import UniversalConverter

    # 1. Create a base CBZ file
    img1 = create_dummy_image(800, 1200, "teal")
    chapters_data = [{"title": "Ch 1", "chapter_display": "1", "images": [img1]}]
    source_cbz = str(tmp_path / "origin.cbz")
    CBZBuilder.build_cbz("Origin Manga", chapters_data, source_cbz)

    # 2. Convert CBZ -> AZW3
    azw3_file = UniversalConverter.convert(source_cbz, "azw3", str(tmp_path))
    assert os.path.exists(azw3_file)
    assert os.path.getsize(azw3_file) > 500

    # 3. Convert AZW3 -> EPUB
    epub_file = UniversalConverter.convert(azw3_file, "epub", str(tmp_path))
    assert os.path.exists(epub_file)
    assert os.path.getsize(epub_file) > 500

    # 4. Convert EPUB -> PDF
    pdf_file = UniversalConverter.convert(epub_file, "pdf", str(tmp_path))
    assert os.path.exists(pdf_file)
    assert os.path.getsize(pdf_file) > 500

    # 5. Convert PDF -> CBZ
    cbz_file = UniversalConverter.convert(pdf_file, "cbz", str(tmp_path))
    assert os.path.exists(cbz_file)
    assert os.path.getsize(cbz_file) > 500

def test_split_and_convert(tmp_path):
    from backend.converters.universal_converter import UniversalConverter
    from backend.converters.cbz_builder import CBZBuilder

    # Create a 6-page CBZ
    imgs = [create_dummy_image(800, 1200, "pink") for _ in range(6)]
    chapters_data = [{"title": "Ch 1", "chapter_display": "1", "images": imgs}]
    source_cbz = str(tmp_path / "long_manga.cbz")
    CBZBuilder.build_cbz("Long Manga", chapters_data, source_cbz)

    # Split into 3 parts (2 pages each)
    split_dir = str(tmp_path / "splits")
    parts = UniversalConverter.split_and_convert(source_cbz, "epub", split_dir, split_mode="parts", split_value=3)
    assert len(parts) == 3
    for p in parts:
        assert os.path.exists(p)
        assert p.endswith(".epub")

def test_kfx_builder(tmp_path):
    from backend.converters.kfx_builder import KFXBuilder
    from backend.converters.universal_converter import UniversalConverter

    imgs = [create_dummy_image(800, 1200, "cyan"), create_dummy_image(800, 1200, "magenta")]
    chapters_data = [{"title": "Chapter 1", "chapter_display": "1", "images": imgs}]
    out_kfx = str(tmp_path / "test_book.kfx")

    KFXBuilder.build_kfx("Test KFX Book", chapters_data, out_kfx, author="MangaDrop")
    assert os.path.exists(out_kfx)
    assert os.path.getsize(out_kfx) > 1000

    with open(out_kfx, "rb") as f:
        data = f.read()
        assert b"BOOK" in data
        assert b"CONT" in data
        assert b"EBOK" in data

    # Test UniversalConverter round-trip to KFX
    kfx_converted = UniversalConverter.convert(out_kfx, "epub", str(tmp_path))
    assert os.path.exists(kfx_converted)
    assert kfx_converted.endswith(".epub")
