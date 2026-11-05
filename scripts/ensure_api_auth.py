from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def _value(lines: list[str], key: str) -> str:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def ensure_api_auth(path: Path) -> bool:
    """Add a single production API key only when neither auth mode is configured."""
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if _value(lines, "TEXT2SQL_API_KEY") or _value(lines, "TEXT2SQL_API_KEYS_JSON"):
        return False

    replacement = f"TEXT2SQL_API_KEY={secrets.token_urlsafe(32)}"
    for index, line in enumerate(lines):
        if line.startswith("TEXT2SQL_API_KEY="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)

    temporary = path.with_name(f".{path.name}.auth.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ensure an ignored deployment .env has API authentication"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    created = ensure_api_auth(args.env_file)
    print("API authentication generated" if created else "API authentication already configured")


if __name__ == "__main__":
    main()
