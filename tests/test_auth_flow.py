import importlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tests.service_loader import load_service


class AsyncTestSession:
    """Async service interface over a real, local SQLite transaction for HTTP tests."""

    def __init__(self, session):
        self.session = session

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def flush(self):
        self.session.flush()

    async def get(self, model, key):
        return self.session.get(model, key)

    async def delete(self, instance):
        self.session.delete(instance)

    def add(self, instance):
        self.session.add(instance)


def test_register_login_refresh_logout_http_with_persistence(keys):
    module = load_service("api-gateway")
    database = importlib.import_module("app.database")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    database.Base.metadata.create_all(engine)

    async def get_db():
        with Session(engine) as session:
            yield AsyncTestSession(session)
            session.commit()

    module.app.dependency_overrides[database.get_db] = get_db
    try:
        with TestClient(module.app) as client:
            payload = {"email": "user@example.com", "password": "Password1"}
            response = client.post("/api/v1/auth/register", json=payload)
            assert response.status_code == 201
            user_id = response.json()["data"]["id"]
            assert client.post("/api/v1/auth/register", json=payload).status_code == 422
            assert (
                client.post("/api/v1/auth/login", json={**payload, "password": "wrong"}).status_code
                == 401
            )
            response = client.post("/api/v1/auth/login", json=payload)
            assert response.status_code == 200
            tokens = response.json()["data"]
            response = client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]}
            )
            assert response.status_code == 200
            assert response.json()["data"]["id"] == user_id
            assert "hashed_password" not in response.text
            response = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            assert response.status_code == 200
            replacement = response.json()["data"]["refresh_token"]
            assert replacement != tokens["refresh_token"]
            assert (
                client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
                ).status_code
                == 401
            )
            assert (
                client.post("/api/v1/auth/logout", json={"refresh_token": replacement}).status_code
                == 200
            )
            assert (
                client.post("/api/v1/auth/refresh", json={"refresh_token": replacement}).status_code
                == 401
            )
    finally:
        module.app.dependency_overrides.clear()
        engine.dispose()
