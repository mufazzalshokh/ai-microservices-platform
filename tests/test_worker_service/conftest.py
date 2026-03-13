from __future__ import annotations

import os
import sys

import pytest

_ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WORKER = os.path.join(_ROOT, "worker-service")


def _load_worker(module_path: str):
    for p in list(sys.path):
        if any(s in p for s in ("api-gateway", "document-service", "ai-service", "worker-service")):
            sys.path.remove(p)
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.path.insert(0, _WORKER)

    import importlib
    return importlib.import_module(module_path)


@pytest.fixture(scope="session")
def celery_app():
    return _load_worker("app.celery_app").celery_app


@pytest.fixture(scope="session")
def document_tasks(celery_app):
    import app.tasks.document_tasks as mod
    return mod


@pytest.fixture(scope="session")
def ai_tasks(celery_app):
    import app.tasks.ai_tasks as mod
    return mod
