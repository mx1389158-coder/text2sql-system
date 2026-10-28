from __future__ import annotations

import argparse
import io
from pathlib import Path

from deploy_virtualbox import run, wait_for_ssh


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure DNS inside the isolated Text2SQL VirtualBox guest"
    )
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument("--interface", default="enp0s3")
    parser.add_argument("--servers", nargs="+", default=["223.5.5.5", "1.1.1.1"])
    args = parser.parse_args()

    password = args.password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("password file is empty")
    servers = " ".join(args.servers)
    client = wait_for_ssh(args.host, args.port, args.username, password, timeout=60)
    try:
        remote_config = f"/home/{args.username}/99-text2sql-dns.yaml"
        yaml = (
            "network:\n"
            "  version: 2\n"
            "  ethernets:\n"
            f"    {args.interface}:\n"
            "      dhcp4: true\n"
            "      dhcp4-overrides:\n"
            "        use-dns: false\n"
            "      nameservers:\n"
            f"        addresses: [{', '.join(args.servers)}]\n"
        )
        with client.open_sftp() as sftp:
            sftp.putfo(io.BytesIO(yaml.encode("utf-8")), remote_config)
        run(
            client,
            "sudo -S install -o root -g root -m 600 "
            f"{remote_config} /etc/netplan/99-text2sql-dns.yaml",
            password=password,
            timeout=60,
        )
        run(client, "sudo -S netplan generate", password=password, timeout=60)
        with client.open_sftp() as sftp:
            sftp.remove(remote_config)
        run(
            client,
            f"sudo -S resolvectl dns {args.interface} {servers}",
            password=password,
            timeout=60,
        )
        run(
            client,
            f"sudo -S resolvectl domain {args.interface} '~.'",
            password=password,
            timeout=60,
        )
        result = run(
            client,
            "getent ahostsv4 registry-1.docker.io | head -n 1",
            timeout=60,
        ).strip()
    finally:
        client.close()
    if not result:
        raise RuntimeError("Docker registry still does not resolve after DNS override")
    print("Docker registry DNS resolution is ready and persistent in the isolated VM.")


if __name__ == "__main__":
    main()
