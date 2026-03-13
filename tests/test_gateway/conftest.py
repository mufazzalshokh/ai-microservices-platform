from __future__ import annotations

import os
import sys
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_GW   = os.path.join(_ROOT, "api-gateway")


@pytest.fixture(scope="session")
def client():
    # Wipe all service paths and cached app modules, then load gateway cleanly
    for p in list(sys.path):
        if "api-gateway" in p or "document-service" in p:
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _GW)

    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)
