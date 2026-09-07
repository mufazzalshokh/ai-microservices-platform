"""Run the same Python quality gates locally and in both CI providers."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("api-gateway", "ai-service", "document-service", "mcp-gateway", "worker-service")


def run(*args: str, cwd: Path = ROOT) -> None:
    command = [sys.executable, *args]
    print("Running: " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    run(
        "-m",
        "compileall",
        "-q",
        "shared/shared",
        "scripts",
        "tests",
        *[f"{s}/app" for s in SERVICES],
    )
    run("-m", "ruff", "check", ".")
    run("-m", "mypy", "--config-file", "pyproject.toml", "shared/shared", "scripts")
    # Independent deployments each use the package name app; check them separately.
    for service in SERVICES:
        run(
            "-m",
            "mypy",
            "--config-file",
            str(ROOT / "pyproject.toml"),
            "--cache-dir",
            str(ROOT / ".mypy_cache"),
            "app",
            cwd=ROOT / service,
        )
    run("-m", "pytest", "tests/", "-q", "--junitxml=test-results.xml")
