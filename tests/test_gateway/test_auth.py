from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


def test_health_reachable():
    client = get_client()
    response = client.get("/health")
    assert response.status_code in (200, 503)
    assert "status" in response.json()


def test_register_password_too_short():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "Short1"},
    )
    assert response.status_code == 422


def test_register_password_no_uppercase():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "nouppercase1"},
    )
    assert response.status_code == 422


def test_register_password_no_digit():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "NoDigitPass"},
    )
    assert response.status_code == 422


def test_register_invalid_email():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Password1"},
    )
    assert response.status_code == 422


def test_me_no_token():
    client = get_client()
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_invalid_token():
    client = get_client()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert response.status_code == 401


def test_root_returns_service_info():
    client = get_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "api-gateway"
    assert "docs" in body
