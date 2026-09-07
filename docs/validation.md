# Local validation evidence

Snapshot: 2026-09-07, Windows, Python 3.12.10. Application images target Python
3.11; CI is configured for both 3.11 and 3.12. Hosted CI was not executed locally.

## Baseline

The checkout began clean on `main`, aligned with its local `origin/main` reference, at
`C:/Users/Lenovo/VS projects/ai-microservices-platform`.

Before publication, fetching the remote revealed 37 newer commits through
`ebc1725`. The feature branch was rebased onto that revision, preserving its
dependency/import fixes and documented lint exclusions. The complete quality gate
was rerun after integration.

- `python -m pip install -r requirements-dev.txt` initially failed on the literal
  `echo` requirement. Development requirements also lacked `pgvector`.
- The system-Python test attempt produced 50 setup errors because `shared` was not
  installed. After correcting dependencies and installing into `.venv`,
  `.venv/Scripts/python -m pytest tests/ -q --tb=short` passed all 50 baseline tests
  in 33.16 seconds, before application behavior changed.
- Baseline Ruff reported 84 issues. Compilation and Compose configuration passed.
- Positive login coverage later exposed a pre-existing Passlib/bcrypt compatibility
  failure that the original negative/structural tests did not exercise.

## Final executable checks

Commands below were run from the repository root using its virtual environment.

| Command | Result |
| --- | --- |
| `.venv/Scripts/python -m pip install -r requirements-dev.txt` | Passed; final editable package metadata installed |
| `.venv/Scripts/python -m pip check` | Passed; no broken requirements |
| `.venv/Scripts/python scripts/check.py` | Passed; compilation, Ruff, all configured mypy targets, pytest |
| Full pytest inside that command | 106 passed in 26.33 seconds after integration; no skips |
| `docker compose --env-file .env.example --profile examples config --quiet` | Passed without reading the local `.env` |
| `git diff --check` | Passed |

The shared command checks shared code/scripts and each independent `app` package
with the root non-strict mypy policy and Pydantic plugin. Both CI providers call it.
SDK versions exercised: official MCP 2.2.0, PydanticAI 2.40.0, FastMCP client 4.0.3.

Tests include asymmetric JWT rejection/acceptance, scopes, public JWKS, refresh
rotation/replay, key generation, deterministic database ownership predicates,
HTTP MCP auth/tools/failures, request/response bounds, and concurrent REST agent
requests through real MCP HTTP transport with deterministic model responses.
Registration/login/profile/refresh/logout are also tested through HTTP with actual
SQLite persistence. SQLite does not establish PostgreSQL row-lock behavior;
PostgreSQL locking and vector execution still require integration validation.

## Structural checks and unavailable checks

Docker 28.4.0 and Compose v2.39.2-desktop.1 are installed. The Linux engine was
initially absent. Starting Docker Desktop failed with an engine error and Windows
paging-file/resource exhaustion. The processes started for that attempt were stopped.
No containers, volumes, database contents, or Git history were deleted or reset.

Consequently these are **not verified in built/running containers**: image builds,
nginx syntax/runtime routing, service startup, healthcheck execution, real PostgreSQL
registration/refresh/locking, pgvector queries, and targeted Celery worker ping.
Dockerfile/Compose definitions and key-mount boundaries were inspected and tested
structurally. Python healthchecks no longer depend on curl and require `status: ok`.

GitHub/GitLab YAML parses and both specify equivalent Python gates and image builds.
No hosted pipeline success is claimed. GitLab's Docker-in-Docker job requires the
privileged TLS-enabled runner setup described in README.

Searches found no private PEM material or removed symmetric-secret configuration in
project changes. The remaining HS256 reference is an intentional rejection test.
The existing `.env` was not modified.
