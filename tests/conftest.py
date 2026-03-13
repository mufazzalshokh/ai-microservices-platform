from __future__ import annotations
import os

os.environ.setdefault("POSTGRES_USER", "testuser")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")
os.environ.setdefault("POSTGRES_DB", "testdb")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AI_SERVICE_URL", "http://localhost:8001")
os.environ.setdefault("DOCUMENT_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
