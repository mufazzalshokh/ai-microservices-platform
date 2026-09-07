"""Load independent services that intentionally share the package name app."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("api-gateway", "ai-service", "document-service", "worker-service", "mcp-gateway")


def load_service(service: str, module: str = "app.main"):
    for path in list(sys.path):
        if any(str(ROOT / name) == path for name in SERVICES):
            sys.path.remove(path)
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    sys.path.insert(0, str(ROOT / service))
    return importlib.import_module(module)
