from __future__ import annotations

import argparse
from pathlib import Path

from deploy_virtualbox import run, wait_for_ssh


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the isolated VM deployment over SSH")
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--diagnose-network", action="store_true")
    args = parser.parse_args()
    password = args.password_file.read_text(encoding="utf-8").strip()
    client = wait_for_ssh(args.host, args.port, args.username, password, timeout=30)
    try:
        root = f"/home/{args.username}/text2sql-system"
        print(run(client, f"cd {root} && docker compose ps"))
        if args.logs:
            print(run(client, f"cd {root} && docker compose logs --tail 80 postgres api web"))
        if args.docker:
            print(
                run(
                    client,
                    "docker image ls; docker ps -a; "
                    "ps -eo pid,etime,cmd | grep -E 'docker compose|buildkit' | grep -v grep || true; "
                    "ss -tpn | grep -E 'dockerd|containerd' || true",
                )
            )
        if args.registry:
            print(
                run(
                    client,
                    "getent ahostsv4 docker.m.daocloud.io; "
                    "curl -I --connect-timeout 10 --max-time 20 "
                    "https://docker.m.daocloud.io/v2/ || true; "
                    "curl -I --connect-timeout 10 --max-time 20 "
                    "https://mirrors.aliyun.com/pypi/simple/ || true; "
                    "curl -I --connect-timeout 10 --max-time 20 "
                    "https://registry.npmmirror.com/ || true; "
                    f"cd {root} && DOCKER_REGISTRY_PREFIX="
                    "m.daocloud.io/docker.io/library/ docker compose config --images",
                )
            )
        if args.diagnose_network:
            print(
                run(
                    client,
                    "resolvectl status; "
                    "printf '\\nDocker registry lookup:\\n'; "
                    "getent ahostsv4 registry-1.docker.io || true; "
                    "printf '\\nDefault route:\\n'; ip route show default; "
                    "printf '\\nNetplan:\\n'; "
                    "for file in /etc/netplan/*.yaml; do "
                    "echo \"--- $file\"; sed -n '1,120p' \"$file\" 2>/dev/null || true; done",
                )
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
