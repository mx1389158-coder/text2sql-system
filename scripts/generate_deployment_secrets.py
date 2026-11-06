from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ALPHABET = string.ascii_letters + string.digits


def secret(length: int = 32) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def write_new(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing secret file: {path}")
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local deployment secrets without printing them")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    admin_password = secret()
    readonly_password = secret()
    vm_password = secret(24)
    api_key = secret(40)
    evaluation_api_key = secret(40)
    env = "\n".join(
        [
            "TEXT2SQL_ENV=production",
            "TEXT2SQL_API_KEY=",
            f'TEXT2SQL_API_KEYS_JSON={{"{api_key}":"default","{evaluation_api_key}":"evaluation"}}',
            "TEXT2SQL_LLM_PROVIDER=demo",
            "TEXT2SQL_BIND_HOST=127.0.0.1",
            "TEXT2SQL_WEB_BIND_HOST=0.0.0.0",
            "TEXT2SQL_POSTGRES_PORT=15432",
            "TEXT2SQL_REDIS_PORT=16379",
            "TEXT2SQL_API_PORT=18000",
            "TEXT2SQL_WEB_PORT=15173",
            f"POSTGRES_ADMIN_PASSWORD={admin_password}",
            f"TEXT2SQL_READONLY_PASSWORD={readonly_password}",
            "",
        ]
    )
    write_new(ROOT / ".env", env, args.force)
    write_new(WORKSPACE / "virtualbox-password.txt", vm_password + "\n", args.force)
    print(f"created {ROOT / '.env'}")
    print(f"created {WORKSPACE / 'virtualbox-password.txt'}")


if __name__ == "__main__":
    main()
