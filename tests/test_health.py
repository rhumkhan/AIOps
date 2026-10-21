"""Smoke test for GET /health.

Uses FastAPI's built-in TestClient (powered by httpx) to call the
endpoint in-memory — no real server or Docker needed.

Run with:  pytest tests/test_health.py -v
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_returns_200():
    """The endpoint must respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_correct_body():
    """The response body must be exactly {"status": "healthy"}."""
    response = client.get("/health")
    assert response.json() == {"status": "healthy"}


def test_health_content_type_is_json():
    """The response must declare JSON content type."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
