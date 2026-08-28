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

def test_kindle_hub_view():
    response = client.get("/kindle")
    assert response.status_code == 200
    assert "Kindle Hub" in response.text

def test_network_ip():
    response = client.get("/api/network/ip")
    assert response.status_code == 200
    data = response.json()
    assert "local_ip" in data
    assert "hub_url" in data


