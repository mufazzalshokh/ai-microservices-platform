"""Build and smoke-test a disposable, externally isolated Compose stack."""

import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Fail before generating keys or creating resources when the engine is unavailable.
    subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, timeout=30)
    project = "ai-platform-smoke-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        temporary = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/generate_keys.py"), "--directory", directory],
            check=True,
        )
        env_file = temporary / "smoke.env"
        env_file.write_text(
            "\n".join(
                [
                    "POSTGRES_USER=smoke",
                    "POSTGRES_DB=smoke",
                    "POSTGRES_PASSWORD=" + secrets.token_hex(24),
                    "JWT_PRIVATE_KEY_PATH=" + (temporary / "jwt-private.pem").as_posix(),
                    "JWT_PUBLIC_KEY_PATH=" + (temporary / "jwt-public.pem").as_posix(),
                    "JWT_ISSUER=http://localhost",
                    "JWT_AUDIENCE=ai-platform",
                    "MCP_RESOURCE_URL=http://localhost/mcp",
                    "OPENAI_API_KEY=smoke-fixture-only",
                    "LOCAL_UID=" + str(os.getuid() if hasattr(os, "getuid") else 1000),
                    "LOCAL_GID=" + str(os.getgid() if hasattr(os, "getgid") else 1000),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(ROOT / "tests/smoke/compose.yml"),
            "--profile",
            "examples",
        ]
        # Prevent shell/CI variables from overriding the disposable configuration.
        environment = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                ("POSTGRES_", "JWT_", "MCP_", "OPENAI_", "LOCAL_", "COMPOSE_", "LLM_", "AGENT_")
            )
        }

        def compose(*args, input=None, check=True, timeout=600):
            return subprocess.run(
                command + list(args),
                cwd=ROOT,
                env=environment,
                input=input,
                text=True,
                check=check,
                timeout=timeout,
            )

        try:
            compose("config", "--quiet")
            compose("build", timeout=1200)
            compose("up", "--detach", "--wait", "--wait-timeout", "180", timeout=240)
            compose("exec", "-T", "nginx", "nginx", "-t")
            compose(
                "exec",
                "-T",
                "api-gateway",
                "python",
                "-",
                input=(ROOT / "tests/smoke/probe.py").read_text(encoding="utf-8"),
                timeout=180,
            )
            print("PASS container smoke suite (including Compose worker health)", flush=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            compose("ps", "--all", check=False, timeout=30)
            compose("logs", "--no-color", "--tail", "80", check=False, timeout=30)
            raise
        finally:
            # This unique project owns only resources created by this invocation.
            # No user stack, images or existing database volumes are removed.
            compose("down", "--volumes", "--remove-orphans", timeout=120)


if __name__ == "__main__":
    main()
