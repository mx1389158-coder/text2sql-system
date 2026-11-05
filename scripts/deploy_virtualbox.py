from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import time
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path


def wait_for_ssh(host: str, port: int, username: str, password: str, timeout: int):
    import paramiko

    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )
            return client
        except (OSError, paramiko.SSHException) as error:
            last_error = type(error).__name__
            client.close()
            time.sleep(10)
    raise TimeoutError(f"SSH did not become ready within {timeout}s ({last_error})")


def run(client, command: str, password: str | None = None, timeout: int = 1800) -> str:
    stdin, stdout, stderr = client.exec_command(command, get_pty=password is not None, timeout=timeout)
    if password is not None:
        stdin.write(password + "\n")
        stdin.flush()
    channel = stdout.channel
    output_chunks: list[bytes] = []
    error_chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while not channel.exit_status_ready():
        if channel.recv_ready():
            output_chunks.append(channel.recv(65536))
        if channel.recv_stderr_ready():
            error_chunks.append(channel.recv_stderr(65536))
        if time.monotonic() >= deadline:
            channel.close()
            raise TimeoutError(f"remote command timed out after {timeout}s")
        time.sleep(0.1)
    while channel.recv_ready():
        output_chunks.append(channel.recv(65536))
    while channel.recv_stderr_ready():
        error_chunks.append(channel.recv_stderr(65536))
    exit_code = channel.recv_exit_status()
    output = b"".join(output_chunks).decode("utf-8", errors="replace")
    error = b"".join(error_chunks).decode("utf-8", errors="replace")
    if exit_code:
        detail = (output + "\n" + error).strip()[-12000:]
        raise RuntimeError(f"remote command failed ({exit_code}): {detail}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy the project archive to the isolated Docker VM")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional ignored .env to upload atomically without logging its contents",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument(
        "--registry-prefix",
        default="",
        help="Optional explicit image prefix, for example m.daocloud.io/docker.io/library/",
    )
    parser.add_argument("--pip-index-url", default="https://pypi.org/simple")
    parser.add_argument("--npm-registry", default="https://registry.npmjs.org")
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument(
        "--report", type=Path, default=Path("infra/virtualbox/deployment-report.json")
    )
    args = parser.parse_args()
    archive = args.archive.resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive)
    password = args.password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("password file is empty")
    env_file = args.env_file.resolve() if args.env_file else None
    if env_file is not None and not env_file.is_file():
        raise FileNotFoundError(env_file)
    registry_prefix = args.registry_prefix.strip()
    if registry_prefix and not re.fullmatch(r"[A-Za-z0-9._:/-]+/", registry_prefix):
        raise ValueError("registry prefix contains unsupported characters or lacks a trailing slash")
    for label, url in (("pip index", args.pip_index_url), ("npm registry", args.npm_registry)):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            raise ValueError(f"{label} must be an HTTP(S) URL without credentials")
    compose_values = {
        "PIP_INDEX_URL": args.pip_index_url,
        "NPM_REGISTRY": args.npm_registry,
    }
    if registry_prefix:
        compose_values["DOCKER_REGISTRY_PREFIX"] = registry_prefix
    compose_env = "".join(
        f"{key}={shlex.quote(value)} " for key, value in compose_values.items()
    )

    client = wait_for_ssh(
        args.host, args.port, args.username, password, timeout=args.wait_seconds
    )
    try:
        key = client.get_transport().get_remote_server_key()
        fingerprint = hashlib.sha256(key.asbytes()).hexdigest()
        remote_archive = f"/home/{args.username}/text2sql-system.tar.gz"
        remote_root = f"/home/{args.username}/text2sql-system"
        remote_env_upload = f"/home/{args.username}/.text2sql-env-upload"
        with client.open_sftp() as sftp:
            sftp.put(str(archive), remote_archive)
            if env_file is not None:
                sftp.put(str(env_file), remote_env_upload)
        run(client, f"mkdir -p {remote_root}")
        run(client, f"tar -xzf {remote_archive} -C {remote_root}")
        if env_file is not None:
            run(
                client,
                f"chmod 600 {remote_env_upload} && "
                f"mv {remote_env_upload} {remote_root}/.env",
            )
        run(client, f"cd {remote_root} && {compose_env}docker compose config --quiet")
        run(
            client,
            f"cd {remote_root} && {compose_env}docker compose up --build -d",
            timeout=3600,
        )
        compose_status = run(client, f"cd {remote_root} && docker compose ps --format json")
        docker_version = run(client, "docker --version").strip()
        compose_version = run(client, "docker compose version").strip()
        os_release = run(client, ". /etc/os-release && printf '%s %s' \"$NAME\" \"$VERSION_ID\"").strip()
    finally:
        client.close()

    report = {
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "port": args.port,
        "vm": "nebula-text2sql-docker",
        "ssh_host_key_sha256": fingerprint,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "os": os_release,
        "docker": docker_version,
        "compose": compose_version,
        "registry_prefix": registry_prefix or None,
        "pip_index_url": args.pip_index_url,
        "npm_registry": args.npm_registry,
        "env_uploaded": env_file is not None,
        "compose_status": [
            json.loads(line) for line in compose_status.splitlines() if line.strip()
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
