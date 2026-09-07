from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_private_signing_material_is_mounted_only_in_issuer():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name, service in compose["services"].items():
        mounts = service.get("secrets", [])
        environment = service.get("environment", {})
        if name == "api-gateway":
            assert "jwt_private_key" in mounts
            assert "JWT_PRIVATE_KEY_PATH" in environment
        else:
            assert "jwt_private_key" not in mounts
            assert "JWT_PRIVATE_KEY_PATH" not in environment
            assert not any("keys" in str(v) for v in service.get("volumes", []))
        if name in {"ai-service", "document-service", "mcp-gateway"}:
            assert mounts == ["jwt_public_key"]
            assert environment["JWT_ALGORITHM"] == "RS256"
    assert compose["services"]["worker"]["profiles"] == ["examples"]


def test_healthchecks_have_available_commands_and_check_status():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name in ("api-gateway", "ai-service", "document-service", "mcp-gateway"):
        command = compose["services"][name]["healthcheck"]["test"]
        assert command[:3] == ["CMD", "python", "-c"]
        compile(command[3], "healthcheck", "exec")
        assert "['status'] == 'ok'" in command[3]
    assert (
        "--destination celery@$$HOSTNAME" in compose["services"]["worker"]["healthcheck"]["test"][1]
    )


def test_both_ci_providers_run_same_python_gate():
    github = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    gitlab = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    assert any(
        step.get("run") == "python scripts/check.py" for step in github["jobs"]["quality"]["steps"]
    )
    assert "python scripts/check.py" in gitlab["quality"]["script"]
    assert (
        "docker compose --env-file .env.example --profile examples build"
        in gitlab["containers"]["script"]
    )
