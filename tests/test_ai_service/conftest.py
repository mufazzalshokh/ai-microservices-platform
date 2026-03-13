from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI   = os.path.join(_ROOT, "ai-service")
_GW   = os.path.join(_ROOT, "api-gateway")
_DOC  = os.path.join(_ROOT, "document-service")


@pytest.fixture(scope="session")
def client():
    for p in list(sys.path):
        if any(svc in p for svc in ("api-gateway", "document-service", "ai-service")):
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _AI)

    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(scope="session")
def prompt_manager():
    for p in list(sys.path):
        if any(svc in p for svc in ("api-gateway", "document-service", "ai-service")):
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _AI)

    from app.services.prompt_manager import PromptManager
    return PromptManager()
