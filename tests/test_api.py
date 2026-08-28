import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_homepage():
    response = client.get("/")
    assert response.status_code == 200
    assert "MangaDrop" in response.text

def test_search_api():
    response = client.get("/api/search?q=One Piece&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "title" in data[0]
        assert "id" in data[0]

def test_scan_mangadex():
    # Test with valid MangaDex ID (One Piece)
    response = client.post(
        "/api/scan",
        json={"url": "https://mangadex.org/title/a1c7c817-4e59-43b7-9365-09675a149a6f", "language": "en"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "One Piece" in data["title"]
    assert len(data["chapters"]) > 0

def test_scan_atsumaru():
    response = client.post(
        "/api/scan",
        json={"url": "https://atsu.moe/manga/NW88G?filter=all", "language": "en"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "Inept Villainess" in data["title"]
    assert len(data["chapters"]) >= 40

def test_send_to_kindle_api():
    # Test Kindle dispatch with a test file
    response = client.post(
        "/api/kindle/send",
        json={
            "file_id": "non_existent_file_id",
            "kindle_email": "nit.ratha01_t9Ucaw@kindle.com"
        }
    )
    # Should return 404 because file_id does not exist
    assert response.status_code == 404

def test_history_api():
    response = client.get("/api/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_kindle_upload():
    import io
    test_file = b"PK\x03\x04 fake epub file content"
    response = client.post(
        "/api/kindle/upload",
        files={"file": ("my_manga.epub", io.BytesIO(test_file), "application/epub+zip")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["filename"] == "my_manga.epub"

def test_convert_upload_api(tmp_path):
    import io
    from PIL import Image
    from backend.converters.cbz_builder import CBZBuilder
    
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_data = buf.getvalue()
    
    cbz_buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(cbz_buf, "w") as zf:
        zf.writestr("001.jpg", img_data)
        
    cbz_bytes = cbz_buf.getvalue()
    
    response = client.post(
        "/api/convert/upload",
        files={"file": ("my_comic.cbz", io.BytesIO(cbz_bytes), "application/vnd.comicbook+zip")},
        data={"target_format": "azw3"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "my_comic.azw3" in data["filename"]
    assert data["format"] == "AZW3"

def test_convert_batch_api():
    import io
    from PIL import Image
    import zipfile
    
    img = Image.new("RGB", (100, 100), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_data = buf.getvalue()
    
    def make_cbz():
        cbz_buf = io.BytesIO()
        with zipfile.ZipFile(cbz_buf, "w") as zf:
            zf.writestr("001.jpg", img_data)
        return cbz_buf.getvalue()
        
    cbz1 = make_cbz()
    cbz2 = make_cbz()
    
    response = client.post(
        "/api/convert/batch",
        files=[
            ("files", ("vol1.cbz", io.BytesIO(cbz1), "application/vnd.comicbook+zip")),
            ("files", ("vol2.cbz", io.BytesIO(cbz2), "application/vnd.comicbook+zip"))
        ],
        data={"target_format": "epub"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_converted"] == 2
    assert "zip_bundle" in data
    assert data["zip_bundle"] is not None





