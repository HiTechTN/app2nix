import pytest
from httpx import ASGITransport, AsyncClient

from app2nix.server import app


@pytest.mark.asyncio
async def test_api_root():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert ".deb" in data["formats"]


@pytest.mark.asyncio
async def test_analyze_no_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/analyze")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_file_too_large():
    big_content = b"0" * (501 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/analyze",
            files={"file": ("big.deb", big_content, "application/octet-stream")},
        )
    assert r.status_code == 413
