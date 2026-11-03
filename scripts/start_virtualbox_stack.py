from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import time
from pathlib import Path

import paramiko


EXPECTED_VM = "nebula-text2sql-docker"


def run(client: paramiko.SSHClient, command: str, timeout: int = 300) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(f"remote command failed ({code}): {(output + error).strip()[-4000:]}")
    return output.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the Compose stack in the dedicated Text2SQL VirtualBox VM"
    )
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument(
        "--deployment-report",
        type=Path,
        default=Path("infra/virtualbox/deployment-report.json"),
    )
    parser.add_argument("--wait-seconds", type=int, default=180)
    args = parser.parse_args()

    password = args.password_file.read_text(encoding="utf-8").strip()
    deployment = json.loads(args.deployment_report.read_text(encoding="utf-8"))
    if not password:
        raise ValueError("password file is empty")
    if deployment.get("vm") != EXPECTED_VM:
        raise ValueError("deployment report is not for the dedicated Text2SQL VM")

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
        remote_root = f"/home/{args.username}/text2sql-system"
        run(
            client,
            f"cd {shlex.quote(remote_root)} && docker compose up -d",
            timeout=600,
        )
        deadline = time.monotonic() + args.wait_seconds
        status = ""
        while time.monotonic() < deadline:
            status = run(
                client,
                f"cd {shlex.quote(remote_root)} && docker compose ps --format json",
            )
            rows = [json.loads(line) for line in status.splitlines() if line.strip()]
            if rows and all(row.get("State") == "running" for row in rows):
                break
            time.sleep(5)
        else:
            raise TimeoutError("dedicated Text2SQL Compose stack did not become running")
    finally:
        client.close()

    print(
        json.dumps(
            {
                "vm": EXPECTED_VM,
                "status": "running",
                "services": [row.get("Service") for row in rows],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
