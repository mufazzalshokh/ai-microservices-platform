from __future__ import annotations
from fastapi.testclient import TestClient


def test_health_reachable(client: TestClient):
    response = client.get("/health")
    assert response.status_code in (200, 503)
    assert "status" in response.json()


def test_upload_no_auth(client: TestClient):
    response = client.post("/api/v1/documents/upload")
    assert response.status_code == 401


def test_list_no_auth(client: TestClient):
    response = client.get("/api/v1/documents/")
    assert response.status_code == 401


def test_search_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test query"},
    )
    assert response.status_code == 401


def test_search_invalid_token(client: TestClient):
    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test query"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


def test_root_returns_service_info(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "document-service"
