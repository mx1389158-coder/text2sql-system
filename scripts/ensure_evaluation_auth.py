from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import tempfile
from pathlib import Path


ALPHABET = string.ascii_letters + string.digits


def _new_key(length: int = 40) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _values(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _replace(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            if not replaced:
                output.append(f"{prefix}{value}")
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(f"{prefix}{value}")
    return output


def ensure_evaluation_scope(path: Path) -> bool:
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    values = _values(lines)
    single_key = values.get("TEXT2SQL_API_KEY", "")
    raw_scoped = values.get("TEXT2SQL_API_KEYS_JSON", "")
    scoped: dict[str, str] = {}
    if raw_scoped:
        parsed = json.loads(raw_scoped)
        if not isinstance(parsed, dict):
            raise ValueError("TEXT2SQL_API_KEYS_JSON must be a JSON object")
        scoped = {str(key): str(scope) for key, scope in parsed.items()}
    if "evaluation" in scoped.values():
        return False
    if single_key:
        scoped.setdefault(single_key, "default")
    if not scoped:
        raise ValueError("configure TEXT2SQL_API_KEY or TEXT2SQL_API_KEYS_JSON first")
    evaluation_key = _new_key()
    while evaluation_key in scoped:
        evaluation_key = _new_key()
    scoped[evaluation_key] = "evaluation"
    lines = _replace(lines, "TEXT2SQL_API_KEY", "")
    lines = _replace(
        lines,
        "TEXT2SQL_API_KEYS_JSON",
        json.dumps(scoped, ensure_ascii=False, separators=(",", ":")),
    )
    content = "\n".join(lines) + "\n"
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.chmod(temporary, mode)
    temporary.replace(path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add an evaluation-scoped API key without printing or rotating existing keys"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    changed = ensure_evaluation_scope(args.env_file.resolve())
    print("evaluation scope added" if changed else "evaluation scope already configured")


if __name__ == "__main__":
    main()
