import importlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from shared.auth import create_access_token, create_refresh_token, decode_token, hash_password
from shared.exceptions import AuthenticationError

from tests.service_loader import load_service


@pytest.mark.parametrize(
    "service,path,scope",
    [
        ("api-gateway", "/api/v1/auth/me", "profile:read"),
        ("ai-service", "/api/v1/inference/templates", "ai:invoke"),
        ("document-service", "/api/v1/documents/", "documents:read"),
    ],
)
def test_resource_scopes_and_public_only_configuration(keys, service, path, scope):
    module = load_service(service)
    settings = importlib.import_module("app.config").get_settings()
    if service != "api-gateway":
        assert "jwt_private_key_path" not in type(settings).model_fields
    user_id = uuid.uuid4()
    client = TestClient(module.app)
    token = create_access_token(str(user_id), "user@example.com", keys[0])
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    if service == "api-gateway":
        router = importlib.import_module("app.routers.auth")
        user = SimpleNamespace(
            id=user_id, email="user@example.com", is_active=True, created_at=datetime.now(UTC)
        )
        module.app.dependency_overrides[router._get_service] = lambda: SimpleNamespace(
            get_current_user=AsyncMock(return_value=user)
        )
    elif service == "document-service":
        router = importlib.import_module("app.routers.documents")
        mock = AsyncMock(return_value=[])
        module.app.dependency_overrides[router._get_service] = lambda: SimpleNamespace(
            list_documents=mock
        )
    token = create_access_token(str(user_id), "user@example.com", keys[0], scopes=[scope])
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    if service == "document-service":
        mock.assert_awaited_once_with(user_id)
    module.app.dependency_overrides.clear()


def test_jwks_contains_only_public_material(keys):
    module = load_service("api-gateway")
    jwk = TestClient(module.app).get("/.well-known/jwks.json").json()["keys"][0]
    assert set(jwk) == {"kty", "use", "alg", "kid", "n", "e"}
    token = create_access_token(str(uuid.uuid4()), "user@example.com", keys[0])
    assert jwt.decode(token, jwk, algorithms=["RS256"], audience="ai-platform")["sub"]


async def test_login_refresh_and_replay(keys):
    module = load_service("api-gateway", "app.services.auth_service")
    schemas = importlib.import_module("app.schemas")
    settings = importlib.import_module("app.config").get_settings()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="user@example.com",
        is_active=True,
        hashed_password=hash_password("Password1"),
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=user)
    db.get = AsyncMock(return_value=user)
    db.delete = AsyncMock()
    service = module.AuthService(db, settings)
    pair = await service.login(schemas.LoginRequest(email=user.email, password="Password1"))
    assert decode_token(pair.access_token, keys[1]).sub == str(user.id)
    stored = SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(days=7))
    db.scalar.side_effect = [stored, None]
    replacement = await service.refresh(pair.refresh_token)
    assert replacement.refresh_token != pair.refresh_token
    db.delete.assert_awaited_once_with(stored)
    with pytest.raises(AuthenticationError, match="already used"):
        await service.refresh(pair.refresh_token)
    statement = db.scalar.call_args.args[0]
    assert "FOR UPDATE" in str(statement)
    with pytest.raises(AuthenticationError):
        await service.refresh(pair.access_token)
    expired = create_refresh_token(str(user.id), user.email, keys[0], expires_days=-1)
    with pytest.raises(AuthenticationError):
        await service.refresh(expired)


def test_generator_refuses_overwrite_and_restricts_permissions(tmp_path):
    import os

    from scripts.generate_keys import generate

    generate(tmp_path)
    original = (tmp_path / "jwt-private.pem").read_bytes()
    with pytest.raises(FileExistsError):
        generate(tmp_path)
    assert (tmp_path / "jwt-private.pem").read_bytes() == original
    if os.name == "posix":
        assert (tmp_path / "jwt-private.pem").stat().st_mode & 0o777 == 0o600


def test_password_hash_compatibility_and_byte_limit(keys):
    from shared.auth import verify_password

    password = "Password1"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password(password, "invalid hash")
    module = load_service("api-gateway")
    response = TestClient(module.app).post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "A1" + "\u00e9" * 36,
        },
    )
    assert response.status_code == 422


def test_private_material_is_rejected_by_verifier(keys):
    token = create_access_token(str(uuid.uuid4()), "user@example.com", keys[0])
    with pytest.raises(AuthenticationError):
        decode_token(token, keys[0])
