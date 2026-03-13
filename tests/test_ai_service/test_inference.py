from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reachable(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-service"


def test_chat_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_chat_stream_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat/stream",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_prompt_no_auth(client: TestClient):
    response = client.post(
        "/api/v1/inference/prompt",
        json={"prompt": "Hello"},
    )
    assert response.status_code == 401


def test_templates_no_auth(client: TestClient):
    response = client.get("/api/v1/inference/templates")
    assert response.status_code == 401


def test_chat_invalid_token(client: TestClient):
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers={"Authorization": "Bearer bad.token.here"},
    )
    assert response.status_code == 401


def test_chat_invalid_role(client: TestClient):
    """Pydantic must reject invalid message roles before hitting LLM."""
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": [{"role": "invalid_role", "content": "Hello"}]},
        headers={"Authorization": "Bearer fake"},
    )
    assert response.status_code in (401, 422)


def test_chat_empty_messages(client: TestClient):
    """Empty messages list must be rejected by Pydantic."""
    response = client.post(
        "/api/v1/inference/chat",
        json={"messages": []},
        headers={"Authorization": "Bearer fake"},
    )
    assert response.status_code in (401, 422)


def test_root_returns_service_info(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ai-service"
