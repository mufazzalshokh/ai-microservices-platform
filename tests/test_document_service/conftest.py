from __future__ import annotations

import os
import sys
import types
import importlib.util
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DOC  = os.path.join(_ROOT, "document-service")


def _load_module(name: str, filepath: str, package: str | None = None):
    """Load a Python module directly from a file path, bypassing sys.path."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_document_service():
    """
    Load the document-service app by injecting _DOC onto sys.path
    cleanly — wiping all other service paths and cached app modules first.
    """
    # Remove all service paths
    for p in list(sys.path):
        if "api-gateway" in p or "document-service" in p:
            sys.path.remove(p)

    # Wipe all app.* cached modules
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]

    # Now insert document-service ONLY
    sys.path.insert(0, _DOC)

    from app.main import app
    return app


@pytest.fixture(scope="session")
def client():
    app = _load_document_service()
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(scope="session")
def chunk_text():
    """Returns the chunk_text function from document-service chunker."""
    _load_document_service()
    from app.services.chunker import chunk_text as _fn
    return _fn


@pytest.fixture(scope="session")
def extract_text_from_bytes():
    """Returns the extract_text_from_bytes function from document-service chunker."""
    _load_document_service()
    from app.services.chunker import extract_text_from_bytes as _fn
    return _fn
