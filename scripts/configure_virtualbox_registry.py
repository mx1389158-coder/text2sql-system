from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from deploy_virtualbox import run, wait_for_ssh


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure a Docker Hub mirror in the isolated Text2SQL VM"
    )
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument("--mirror", default="https://docker.m.daocloud.io")
    parser.add_argument("--verify-image", action="append", default=[])
    args = parser.parse_args()

    password = args.password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("password file is empty")
    config = json.dumps({"registry-mirrors": [args.mirror]}, indent=2) + "\n"
    remote_config = f"/home/{args.username}/text2sql-daemon.json"
    client = wait_for_ssh(args.host, args.port, args.username, password, timeout=60)
    try:
        existing = run(
            client,
            "if test -f /etc/docker/daemon.json; then cat /etc/docker/daemon.json; fi",
        ).strip()
        if existing and json.loads(existing) != json.loads(config):
            raise RuntimeError("refusing to overwrite an unrelated Docker daemon configuration")
        with client.open_sftp() as sftp:
            sftp.putfo(io.BytesIO(config.encode("utf-8")), remote_config)
        run(
            client,
            "sudo -S install -o root -g root -m 644 "
            f"{remote_config} /etc/docker/daemon.json",
            password=password,
            timeout=60,
        )
        with client.open_sftp() as sftp:
            sftp.remove(remote_config)
        run(client, "sudo -S systemctl restart docker", password=password, timeout=120)
        mirrors = run(
            client, "docker info --format '{{json .RegistryConfig.Mirrors}}'", timeout=60
        ).strip()
        for image in args.verify_image:
            run(client, f"docker pull {image}", timeout=600)
    finally:
        client.close()
    if args.mirror not in mirrors:
        raise RuntimeError("Docker did not activate the configured registry mirror")
    print("Docker registry mirror is active in the isolated VM.")


if __name__ == "__main__":
    main()
