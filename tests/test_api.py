"""HTTP contract smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_endpoint() -> None:
    """The schema route must describe the analyze API for the placement POC."""
    client = TestClient(app)
    response = client.get("/api/schema")
    assert response.status_code == 200
    payload = response.json()
    assert "paths" in payload
    assert "/api/analyze" in payload["paths"]
