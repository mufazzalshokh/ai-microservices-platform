import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 1. Fix shared/pyproject.toml (wrong build backend) ───────────────────────
pyproject = """\
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shared"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "structlog>=24.1",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*"]
"""

with open("shared/pyproject.toml", "w", encoding="utf-8", newline="\n") as f:
    f.write(pyproject)
print("  fixed shared/pyproject.toml")

# ── 2. Create root pyproject.toml (dev tooling config) ───────────────────────
root_pyproject = """\
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = false
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
"""
with open("pyproject.toml", "w", encoding="utf-8", newline="\n") as f:
    f.write(root_pyproject)
print("  wrote root pyproject.toml")

# ── 3. Create .gitignore (professional standard) ──────────────────────────────
gitignore = """\
# Python
__pycache__/
*.py[cod]
*.egg-info/
*.egg
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# Environment files
.env
!.env.example

# Testing
.pytest_cache/
.coverage
htmlcov/
coverage.xml

# Type checking
.mypy_cache/

# Editors
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Docker
*.log
"""
with open(".gitignore", "w", encoding="utf-8", newline="\n") as f:
    f.write(gitignore)
print("  wrote .gitignore")

# ── 4. Create requirements files per service ──────────────────────────────────
reqs = {
    "api-gateway/requirements.txt": """\
fastapi>=0.111
uvicorn[standard]>=0.30
asyncpg>=0.29
sqlalchemy[asyncio]>=2.0
httpx>=0.27
python-multipart>=0.0.9
""",
    "ai-service/requirements.txt": """\
fastapi>=0.111
uvicorn[standard]>=0.30
openai>=1.30
httpx>=0.27
""",
    "document-service/requirements.txt": """\
fastapi>=0.111
uvicorn[standard]>=0.30
asyncpg>=0.29
sqlalchemy[asyncio]>=2.0
python-multipart>=0.0.9
httpx>=0.27
""",
    "worker-service/requirements.txt": """\
celery[redis]>=5.4
asyncpg>=0.29
sqlalchemy[asyncio]>=2.0
httpx>=0.27
""",
}

for path, content in reqs.items():
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  wrote {path}")

# ── 5. Create dev requirements (local tooling) ────────────────────────────────
dev_reqs = """\
# Shared lib
-e shared/

# Shared dependencies (for local dev/testing)
pydantic>=2.7
pydantic-settings>=2.3
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
structlog>=24.1

# All service deps (for running tests locally)
fastapi>=0.111
uvicorn[standard]>=0.30
asyncpg>=0.29
sqlalchemy[asyncio]>=2.0
httpx>=0.27
python-multipart>=0.0.9
openai>=1.30
celery[redis]>=5.4

# Dev tooling
pytest>=8.2
pytest-asyncio>=0.23
pytest-cov>=5.0
ruff>=0.4
mypy>=1.10
"""
with open("requirements-dev.txt", "w", encoding="utf-8", newline="\n") as f:
    f.write(dev_reqs)
print("  wrote requirements-dev.txt")

print("\nAll files fixed and written!")
print("\nNext — run these commands in Git Bash:")
print("  python -m venv .venv")
print("  source .venv/Scripts/activate")
print("  pip install -r requirements-dev.txt")