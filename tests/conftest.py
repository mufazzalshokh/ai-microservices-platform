from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session", autouse=True)
def keys(tmp_path_factory):
    from pydantic_ai import models

    models.ALLOW_MODEL_REQUESTS = False
    directory = tmp_path_factory.mktemp("jwt")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    (directory / "private.pem").write_text(private)
    (directory / "public.pem").write_text(public)
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(directory / "private.pem")
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(directory / "public.pem")
    os.environ["JWT_ISSUER"] = "http://localhost"
    os.environ["JWT_AUDIENCE"] = "ai-platform"
    os.environ["JWT_ALGORITHM"] = "RS256"
    yield private, public
    for path in directory.iterdir():
        Path(path).unlink()


os.environ["POSTGRES_USER"] = "testuser"
os.environ["POSTGRES_PASSWORD"] = "testpass"
os.environ["POSTGRES_DB"] = "testdb"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["AI_SERVICE_URL"] = "http://localhost:8001"
os.environ["DOCUMENT_SERVICE_URL"] = "http://localhost:8002"
os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"
