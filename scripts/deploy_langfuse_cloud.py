from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import time
from pathlib import Path

import paramiko


EXPECTED_VM = "nebula-text2sql-docker"
REMOTE_ROOT = "/home/text2sql/text2sql-system"


def run(client: paramiko.SSHClient, command: str, timeout: int = 1800) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(f"remote command failed ({code}): {(output + error).strip()[-4000:]}")
    return output.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enable Langfuse Cloud on the dedicated Text2SQL VM only"
    )
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument(
        "--deployment-report",
        type=Path,
        default=Path("infra/virtualbox/deployment-report.json"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    args = parser.parse_args()

    deployment = json.loads(args.deployment_report.read_text(encoding="utf-8"))
    if deployment.get("vm") != EXPECTED_VM:
        raise ValueError("deployment report is not for the dedicated Text2SQL VM")
    password = args.password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("password file is empty")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.username,
        password=password,
        timeout=15,
        auth_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        key = client.get_transport().get_remote_server_key()
        fingerprint = hashlib.sha256(key.asbytes()).hexdigest()
        if fingerprint != deployment["ssh_host_key_sha256"]:
            raise RuntimeError("SSH host key does not match the dedicated VM deployment report")

        files = {
            Path(".env"): f"{REMOTE_ROOT}/.env",
            Path("docker-compose.yml"): f"{REMOTE_ROOT}/docker-compose.yml",
            Path("apps/api/app/core/config.py"): f"{REMOTE_ROOT}/apps/api/app/core/config.py",
        }
        with client.open_sftp() as sftp:
            for local_path, remote_path in files.items():
                sftp.put(str(local_path), remote_path)

        compose_values = {
            "DOCKER_REGISTRY_PREFIX": deployment.get("registry_prefix") or "",
            "PIP_INDEX_URL": deployment.get("pip_index_url") or "https://pypi.org/simple/",
            "NPM_REGISTRY": deployment.get("npm_registry") or "https://registry.npmjs.org/",
        }
        compose_env = " ".join(
            f"{name}={shlex.quote(value)}" for name, value in compose_values.items()
        )
        root = shlex.quote(REMOTE_ROOT)
        run(client, f"cd {root} && {compose_env} docker compose config --quiet")
        run(client, f"cd {root} && {compose_env} docker compose up --build -d api")

        deadline = time.monotonic() + 180
        status = ""
        while time.monotonic() < deadline:
            status = run(client, f"cd {root} && docker compose ps --format json api")
            rows = [json.loads(line) for line in status.splitlines() if line.strip()]
            if rows and rows[0].get("State") == "running" and rows[0].get("Health") == "healthy":
                break
            time.sleep(5)
        else:
            raise TimeoutError("Text2SQL API did not become healthy after Langfuse configuration")

        config_status = run(
            client,
            f"cd {root} && docker compose exec -T api python -c "
            + shlex.quote(
                "from apps.api.app.core.config import Settings; "
                "s=Settings.from_environment(); "
                "print({'host': bool(s.langfuse_host), "
                "'public_key': bool(s.langfuse_public_key), "
                "'secret_key': bool(s.langfuse_secret_key)})"
            ),
        )
    finally:
        client.close()

    print(
        json.dumps(
            {
                "vm": EXPECTED_VM,
                "api_status": "healthy",
                "langfuse_configuration": config_status,
                "updated_files": [str(path) for path in files],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
