"""Tests for app2nix server API"""


from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def test_api_root():
    """Test API root endpoint"""
    response = client.get("/api")
    assert response.status_code == 200
    assert "version" in response.json()


def test_root_returns_html():
    """Test root returns HTML"""
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_analyze_invalid_file():
    """Test analyze with invalid file type"""
    data = {"file": ("test.txt", b"test", "text/plain")}
    response = client.post("/analyze", files=data)
    assert response.status_code == 400


def test_download_invalid_url():
    """Test download endpoint does not exist (not implemented)"""
    response = client.post("/download", json={"url": "https://example.com/file.txt"})
    assert response.status_code == 404
